#!/usr/bin/env python3
"""
Simulator Log Parser

Parses ns-3 simulator output logs and extracts performance metrics.
These metrics are used to calculate the reward score and provide
feedback to the LLM for adaptive fuzzing.
"""

import re
from pathlib import Path
from typing import Dict, Optional


class SimulatorLogParser:
    """
    Parses simulator logs to extract performance metrics.
    
    Expected log format (flexible regex-based parsing):
      - Frames received: <number>
      - Frames forwarded: <number>
      - Frames dropped (policing): <number>
      - Frames dropped (invalid VL): <number>
      - Malformed frames accepted: <number>  [BUG INDICATOR!]
    """
    
    # Regex patterns for different metric types
    PATTERNS = {
        "frames_received": r"frames?\s+received[:\s]+(\d+)",
        "frames_forwarded": r"frames?\s+forwarded[:\s]+(\d+)",
        "frames_dropped_policing": r"frames?\s+dropped\s*\(policing\)[:\s]+(\d+)",
        "frames_dropped_invalid_vl": r"frames?\s+dropped\s*\(invalid\s+vl\)[:\s]+(\d+)",
        "frames_dropped_total": r"frames?\s+dropped[:\s]+(\d+)",
        "malformed_accepted": r"malformed.*accepted[:\s]+(\d+)",
        "simulation_time": r"simulation\s+time[:\s]+([\d.]+)",
    }
    
    def __init__(self, log_content: Optional[str] = None, log_file: Optional[str] = None):
        """
        Initialize the log parser.
        
        Args:
            log_content: Raw log text (if provided directly)
            log_file: Path to log file (if reading from file)
            
        One of log_content or log_file must be provided.
        
        Raises:
            ValueError: If neither log_content nor log_file is provided
            FileNotFoundError: If log_file doesn't exist
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
            raise ValueError("Either log_content or log_file must be provided")
        
        self.metrics = None
    
    def _parse_csv(self) -> Dict[str, any]:
        """Parse CSV format from AFDX simulator."""
        import csv
        from io import StringIO
        
        metrics = {
            "frames_received": 0,
            "frames_forwarded": 0,
            "frames_dropped_policing": 0,
            "frames_dropped_invalid_vl": 0,
            "frames_dropped_total": 0,
            "malformed_accepted": 0,
            "simulation_time_sec": 0.0
        }
        
        try:
            # Parse CSV
            reader = csv.DictReader(StringIO(self.log_content))
            rows = list(reader)
            
            if not rows:
                return metrics
            
            # Count RX events (frames received)
            rx_frames = [r for r in rows if r['Event'] == 'RX']
            metrics["frames_received"] = len(rx_frames)
            
            # Count forwarded (RX frames that went through switches)
            forwarded = [r for r in rx_frames if int(r.get('SwitchHops', 0)) > 0]
            metrics["frames_forwarded"] = len(forwarded)
            
            # Get simulation time from last row
            if rows:
                metrics["simulation_time_sec"] = float(rows[-1]['Timestamp'])
            
            # For now, dropped frames = received - forwarded (simplified)
            metrics["frames_dropped_total"] = metrics["frames_received"] - metrics["frames_forwarded"]
            
            # Malformed frames that were accepted (IntegrityCheckResult = Fail but still received)
            malformed = [r for r in rx_frames if r.get('IntegrityCheckResult') == 'Fail']
            metrics["malformed_accepted"] = len(malformed)
            
        except Exception as e:
            print(f"Warning: CSV parsing failed: {e}")
        
        return metrics
    
    def parse(self) -> Dict[str, any]:
        """
        Parse the log and extract all metrics.
        
        Returns:
            Dictionary containing:
            {
                "frames_received": int,
                "frames_forwarded": int,
                "frames_dropped_policing": int,
                "frames_dropped_invalid_vl": int,
                "frames_dropped_total": int,
                "malformed_accepted": int,  # 0 = good, >0 = BUG!
                "simulation_time_sec": float,
                "parsing_success": bool
            }
        """
        # Check if this is CSV format (from AFDX simulator)
        if "Timestamp,Event," in self.log_content:
            metrics = self._parse_csv()
        else:
            # Parse text log format
            metrics = {}
            
            # Extract each metric using regex
            for metric_name, pattern in self.PATTERNS.items():
                match = re.search(pattern, self.log_content, re.IGNORECASE)
                if match:
                    value = match.group(1)
                    # Convert to appropriate type
                    if metric_name == "simulation_time":
                        metrics["simulation_time_sec"] = float(value)
                    else:
                        metrics[metric_name] = int(value)
                else:
                    # Metric not found - use default
                    if metric_name == "simulation_time":
                        metrics["simulation_time_sec"] = 0.0
                    else:
                        metrics[metric_name] = 0
        
        # Calculate derived metrics (as percentages)
        total_received = metrics.get("frames_received", 0)
        if total_received > 0:
            metrics["forward_rate"] = (metrics.get("frames_forwarded", 0) / total_received) * 100.0
            metrics["drop_rate"] = (metrics.get("frames_dropped_total", 0) / total_received) * 100.0
            metrics["policing_rate"] = (metrics.get("frames_dropped_policing", 0) / total_received) * 100.0
        else:
            metrics["forward_rate"] = 0.0
            metrics["drop_rate"] = 0.0
            metrics["policing_rate"] = 0.0
        
        # Parsing success indicator
        metrics["parsing_success"] = metrics.get("frames_received", 0) > 0
        
        self.metrics = metrics
        return metrics
    
    def get_metric(self, metric_name: str, default: any = 0) -> any:
        """
        Get a specific metric value.
        
        Args:
            metric_name: Name of the metric
            default: Default value if metric not found
            
        Returns:
            Metric value
        """
        if self.metrics is None:
            self.parse()
        return self.metrics.get(metric_name, default)
    
    def has_bugs(self) -> bool:
        """
        Check if the log indicates any bugs (malformed frames accepted).
        
        Returns:
            True if bugs detected, False otherwise
        """
        if self.metrics is None:
            self.parse()
        return self.metrics.get("malformed_accepted", 0) > 0
    
    def summary(self) -> str:
        """
        Get a human-readable summary of the metrics.
        
        Returns:
            Formatted summary string
        """
        if self.metrics is None:
            self.parse()
        
        lines = [
            "SIMULATOR METRICS SUMMARY",
            "=" * 50,
            f"Frames received: {self.metrics.get('frames_received', 0)}",
            f"Frames forwarded: {self.metrics.get('frames_forwarded', 0)} "
            f"({self.metrics.get('forward_rate', 0):.1%})",
            f"Frames dropped (policing): {self.metrics.get('frames_dropped_policing', 0)} "
            f"({self.metrics.get('policing_rate', 0):.1%})",
            f"Frames dropped (invalid VL): {self.metrics.get('frames_dropped_invalid_vl', 0)}",
            f"Frames dropped (total): {self.metrics.get('frames_dropped_total', 0)} "
            f"({self.metrics.get('drop_rate', 0):.1%})",
            f"Malformed accepted: {self.metrics.get('malformed_accepted', 0)} "
            f"{'BUG!' if self.has_bugs() else 'OK'}",
            f"Simulation time: {self.metrics.get('simulation_time_sec', 0):.2f}s",
            "=" * 50
        ]
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test with mock log
    mock_log = """
    [INFO] Starting AFDX simulation...
    [INFO] Frames received: 1000
    [INFO] Frames forwarded: 850
    [INFO] Frames dropped (policing): 100
    [INFO] Frames dropped (invalid VL): 50
    [INFO] Frames dropped: 150
    [INFO] Malformed frames accepted: 0
    [INFO] Simulation time: 10.5s
    """
    
    parser = SimulatorLogParser(log_content=mock_log)
    metrics = parser.parse()
    
    print(parser.summary())
    print(f"\nBugs detected: {parser.has_bugs()}")

