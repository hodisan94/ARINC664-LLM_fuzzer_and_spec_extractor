#!/usr/bin/env python3
"""
Simulator Log Parser

Parses ns-3 simulator output and extracts performance metrics.
Supports two data sources that are combined for full coverage:
  1. CSV (AFDX-LOG-OUTPUT.csv): TX/RX events at end systems
  2. stdout (ExportMIB): Switch-level counters including policing drops
"""

import re
import csv
from io import StringIO
from pathlib import Path
from typing import Dict, Optional


class SimulatorLogParser:
    """
    Parses simulator output to extract performance metrics.

    The ns-3 AFDX simulator produces two complementary outputs:
      - CSV file: per-frame TX/RX events (no policing/drop info)
      - stdout: ExportMIB counters from switches (has policing/drop info)

    This parser can accept both and merges them into a single metrics dict.
    """

    # ExportMIB patterns (stdout from afdx-demo)
    MIB_PATTERNS = {
        "frames_received":         r"afdxFramesReceived\.\d+\s*=\s*(\d+)",
        "frames_forwarded":        r"afdxFramesForwarded\.\d+\s*=\s*(\d+)",
        "frames_dropped_total":    r"afdxFramesDropped\.\d+\s*=\s*(\d+)",
        "frames_dropped_policing": r"afdxFramesDroppedPolicing\.\d+\s*=\s*(\d+)",
        "frames_dropped_invalid_vl": r"afdxFramesDroppedInvalidVL\.\d+\s*=\s*(\d+)",
    }

    # Mutation metrics printed by the C++ demo when mutations are active
    MUTATION_PATTERNS = {
        "mutation_payload_applied": r"AfdxMutation\.payloadAppliedBytes\s*=\s*(-?\d+)",
        "mutation_jitter_applied":  r"AfdxMutation\.jitterAppliedMs\s*=\s*(-?\d+)",
        "mutation_clamp_count":     r"AfdxMutation\.payloadClampCount\s*=\s*(\d+)",
        "mutation_tx_prob_drops":   r"AfdxMutation\.txProbDrops\s*=\s*(\d+)",
        "mutation_mac_spoof_count": r"AfdxMutation\.macSpoofCount\s*=\s*(\d+)",
    }

    # Legacy text-format patterns (kept for backward compatibility)
    LEGACY_PATTERNS = {
        "frames_received":         r"frames?\s+received[:\s]+(\d+)",
        "frames_forwarded":        r"frames?\s+forwarded[:\s]+(\d+)",
        "frames_dropped_policing": r"frames?\s+dropped\s*\(policing\)[:\s]+(\d+)",
        "frames_dropped_invalid_vl": r"frames?\s+dropped\s*\(invalid\s+vl\)[:\s]+(\d+)",
        "frames_dropped_total":    r"frames?\s+dropped[:\s]+(\d+)",
        "malformed_accepted":      r"malformed.*accepted[:\s]+(\d+)",
        "simulation_time":         r"simulation\s+time[:\s]+([\d.]+)",
    }

    def __init__(
        self,
        log_content: Optional[str] = None,
        log_file: Optional[str] = None,
        csv_content: Optional[str] = None,
    ):
        """
        Args:
            log_content: Simulator stdout text (contains ExportMIB data)
            log_file: Path to a log file (alternative to log_content)
            csv_content: CSV text from AFDX-LOG-OUTPUT.csv (optional, for RX counts)
        """
        if log_content:
            self.log_content = log_content
        elif log_file:
            log_path = Path(log_file)
            if not log_path.exists():
                raise FileNotFoundError(f"Log file not found: {log_file}")
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.log_content = f.read()
        else:
            self.log_content = ""

        self.csv_content = csv_content or ""
        self.metrics = None

    # ------------------------------------------------------------------
    # CSV parsing (RX/TX events from end systems)
    # ------------------------------------------------------------------
    def _parse_csv(self) -> Dict[str, int]:
        metrics: Dict[str, int] = {}
        if not self.csv_content:
            return metrics

        try:
            reader = csv.DictReader(StringIO(self.csv_content))
            rows = list(reader)
            if not rows:
                return metrics

            rx_frames = [r for r in rows if r.get('Event') == 'RX']
            metrics["csv_frames_received"] = len(rx_frames)

            forwarded = [r for r in rx_frames if int(r.get('SwitchHops', 0)) > 0]
            metrics["csv_frames_forwarded"] = len(forwarded)

            malformed = [r for r in rx_frames if r.get('IntegrityCheckResult') == 'Fail']
            metrics["malformed_accepted"] = len(malformed)

            if rows:
                metrics["simulation_time_sec"] = float(rows[-1].get('Timestamp', 0))
        except Exception as e:
            print(f"Warning: CSV parsing failed: {e}")

        return metrics

    # ------------------------------------------------------------------
    # ExportMIB parsing (switch statistics from stdout)
    # ------------------------------------------------------------------
    def _parse_mib(self) -> Dict[str, int]:
        """Parse ExportMIB output from stdout. Sums values across switches."""
        metrics: Dict[str, int] = {}
        if not self.log_content:
            return metrics

        for key, pattern in self.MIB_PATTERNS.items():
            total = 0
            for m in re.finditer(pattern, self.log_content):
                total += int(m.group(1))
            if total > 0:
                metrics[key] = total

        for key, pattern in self.MUTATION_PATTERNS.items():
            m = re.search(pattern, self.log_content)
            if m:
                metrics[key] = int(m.group(1))

        return metrics

    def _parse_legacy_text(self) -> Dict[str, int]:
        """Fallback: parse free-text log lines (old mock format)."""
        metrics: Dict[str, int] = {}
        if not self.log_content:
            return metrics

        for key, pattern in self.LEGACY_PATTERNS.items():
            m = re.search(pattern, self.log_content, re.IGNORECASE)
            if m:
                val = m.group(1)
                if key == "simulation_time":
                    metrics["simulation_time_sec"] = float(val)
                else:
                    metrics[key] = int(val)

        return metrics

    # ------------------------------------------------------------------
    # Main parse entry point
    # ------------------------------------------------------------------
    def parse(self) -> Dict[str, any]:
        """
        Parse all available sources and merge into a single metrics dict.

        Priority: ExportMIB (switch-level) > CSV (end-system) > legacy text.
        """
        defaults = {
            "frames_received": 0,
            "frames_forwarded": 0,
            "frames_dropped_policing": 0,
            "frames_dropped_invalid_vl": 0,
            "frames_dropped_total": 0,
            "malformed_accepted": 0,
            "simulation_time_sec": 0.0,
        }

        csv_metrics = self._parse_csv()
        mib_metrics = self._parse_mib()
        legacy_metrics = self._parse_legacy_text()

        merged = dict(defaults)

        # Layer 1: legacy text (lowest priority)
        merged.update({k: v for k, v in legacy_metrics.items() if v})

        # Layer 2: CSV (better for RX counts and malformed detection)
        if csv_metrics.get("csv_frames_received"):
            merged["frames_received"] = csv_metrics["csv_frames_received"]
        if csv_metrics.get("csv_frames_forwarded"):
            merged["frames_forwarded"] = csv_metrics["csv_frames_forwarded"]
        if csv_metrics.get("malformed_accepted"):
            merged["malformed_accepted"] = csv_metrics["malformed_accepted"]
        if csv_metrics.get("simulation_time_sec"):
            merged["simulation_time_sec"] = csv_metrics["simulation_time_sec"]

        # Layer 3: ExportMIB (highest priority — authoritative for switch counters)
        if mib_metrics.get("frames_received"):
            merged["frames_received"] = mib_metrics["frames_received"]
        if mib_metrics.get("frames_forwarded"):
            merged["frames_forwarded"] = mib_metrics["frames_forwarded"]
        if mib_metrics.get("frames_dropped_policing"):
            merged["frames_dropped_policing"] = mib_metrics["frames_dropped_policing"]
        if mib_metrics.get("frames_dropped_invalid_vl"):
            merged["frames_dropped_invalid_vl"] = mib_metrics["frames_dropped_invalid_vl"]
        if mib_metrics.get("frames_dropped_total"):
            merged["frames_dropped_total"] = mib_metrics["frames_dropped_total"]

        # Copy mutation metrics if present
        for key in self.MUTATION_PATTERNS:
            if key in mib_metrics:
                merged[key] = mib_metrics[key]

        # Derived rates
        total = merged["frames_received"]
        if total > 0:
            merged["forward_rate"] = (merged["frames_forwarded"] / total) * 100.0
            merged["drop_rate"] = (merged["frames_dropped_total"] / total) * 100.0
            merged["policing_rate"] = (merged["frames_dropped_policing"] / total) * 100.0
        else:
            merged["forward_rate"] = 0.0
            merged["drop_rate"] = 0.0
            merged["policing_rate"] = 0.0

        merged["parsing_success"] = merged["frames_received"] > 0

        self.metrics = merged
        return merged

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def get_metric(self, metric_name: str, default=0):
        if self.metrics is None:
            self.parse()
        return self.metrics.get(metric_name, default)

    def has_bugs(self) -> bool:
        if self.metrics is None:
            self.parse()
        return self.metrics.get("malformed_accepted", 0) > 0

    def summary(self) -> str:
        if self.metrics is None:
            self.parse()

        m = self.metrics
        lines = [
            "SIMULATOR METRICS SUMMARY",
            "=" * 50,
            f"Frames received: {m.get('frames_received', 0)}",
            f"Frames forwarded: {m.get('frames_forwarded', 0)} "
            f"({m.get('forward_rate', 0):.1f}%)",
            f"Frames dropped (policing): {m.get('frames_dropped_policing', 0)} "
            f"({m.get('policing_rate', 0):.1f}%)",
            f"Frames dropped (invalid VL): {m.get('frames_dropped_invalid_vl', 0)}",
            f"Frames dropped (total): {m.get('frames_dropped_total', 0)} "
            f"({m.get('drop_rate', 0):.1f}%)",
            f"Malformed accepted: {m.get('malformed_accepted', 0)} "
            f"{'BUG!' if self.has_bugs() else 'OK'}",
            f"Simulation time: {m.get('simulation_time_sec', 0):.2f}s",
            "=" * 50,
        ]

        # Show mutation application metrics if present
        if m.get("mutation_payload_applied") is not None:
            lines.insert(-1, f"Mutation payload applied: {m['mutation_payload_applied']} bytes")
        if m.get("mutation_jitter_applied") is not None:
            lines.insert(-1, f"Mutation jitter applied: {m['mutation_jitter_applied']} ms")

        return "\n".join(lines)


if __name__ == "__main__":
    # Test with ExportMIB format (real simulator output)
    mock_stdout = """
=== SWITCH A (Network A) STATISTICS ===
# AFDX Switch MIB Export (SNMP-like format)
# Switch ID: 1
afdxFramesReceived.0 = 7200
afdxFramesForwarded.0 = 7000
afdxFramesDropped.0 = 200
afdxFramesDroppedPolicing.0 = 150
afdxFramesDroppedInvalidVL.0 = 50

=== SWITCH B (Network B) STATISTICS ===
afdxFramesReceived.0 = 7170
afdxFramesForwarded.0 = 7000
afdxFramesDropped.0 = 170
afdxFramesDroppedPolicing.0 = 120
afdxFramesDroppedInvalidVL.0 = 50

=== MUTATION APPLICATION METRICS ===
AfdxMutation.payloadAppliedBytes = 500
AfdxMutation.jitterAppliedMs = -3
AfdxMutation.payloadClampCount = 0
AfdxMutation.txProbDrops = 0
AfdxMutation.macSpoofCount = 0
    """

    parser = SimulatorLogParser(log_content=mock_stdout)
    metrics = parser.parse()

    print(parser.summary())
    print(f"\nBugs detected: {parser.has_bugs()}")
    print(f"Policing rate: {metrics['policing_rate']:.1f}%")
    print(f"Mutation payload applied: {metrics.get('mutation_payload_applied', 'N/A')}")
