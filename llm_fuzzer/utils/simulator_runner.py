#!/usr/bin/env python3
"""
Simulator Runner

Executes the ns-3 AFDX simulator with generated test frames and collects results.
This is the bridge between the test generator and the simulator.
"""

import csv
import subprocess
import json
import os
import shutil
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime


class SimulatorRunner:
    """
    Runs ns-3 simulator with test frames and collects feedback.
    
    Workflow:
    1. Translate Python test_inputs → C++ mutations.json format
    2. Execute ns-3 simulation
    3. Collect output logs (stdout + CSV)
    4. Return results
    """
    
    def __init__(
        self,
        ns3_path: str = "/home/hodisan1994/ns-3-reset/ns-3",
        mutations_file: str = "examples/AFDX_V3/mutations.json",
        output_dir: str = "examples/AFDX_V3/output",
        vl_config_file: str = "examples/AFDX_V3/config/virtual_links.csv",
        skip_ns3_check: bool = False
    ):
        self.ns3_path = Path(ns3_path)
        self.mutations_file = self.ns3_path / mutations_file
        self.output_dir = self.ns3_path / output_dir
        
        self.mutations_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.ns3_script = self.ns3_path / "ns3"
        if not skip_ns3_check and not self.ns3_script.exists():
            raise FileNotFoundError(f"ns3 script not found: {self.ns3_script}")
        
        self.vl_configs = self._load_vl_configs(self.ns3_path / vl_config_file)
    
    def _load_vl_configs(self, csv_path: Path) -> Dict[int, Dict]:
        """Load VL configurations from virtual_links.csv for payload delta computation."""
        configs = {}
        if not csv_path.exists():
            return configs
        with open(csv_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) < 9:
                    continue
                try:
                    vl_id = int(parts[0])
                    configs[vl_id] = {
                        'max_frame_size': int(parts[7]),
                        'min_frame_size': int(parts[8]),
                        'bag_ms': int(parts[6]),
                        'base_size': (int(parts[7]) + int(parts[8])) // 2,
                    }
                except (ValueError, IndexError):
                    continue
        return configs
    
    def run_simulation(
        self,
        test_inputs: Dict[str, Any],
        scenario_name: str = "afdx-demo",
        timeout: int = 60,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run ns-3 simulation with test inputs.
        
        Args:
            test_inputs: Test inputs dictionary from test generator
            scenario_name: ns-3 scenario to run (default: afdx-demo)
            timeout: Simulation timeout in seconds
            run_id: Optional run identifier (generated if not provided)
            
        Returns:
            Dictionary with:
                - success: bool
                - log_content: str (simulator output)
                - error: str (if failed)
                - run_id: str
                - duration: float (seconds)
        """
        if run_id is None:
            run_id = self._generate_run_id()
        
        start_time = time.time()
        
        try:
            # Step 1: Write mutations.json file
            self._write_mutations_file(test_inputs)
            
            # Step 2: Execute simulator
            log_content, stderr_content = self._execute_ns3(
                scenario_name,
                timeout=timeout
            )
            
            # Step 3: Read CSV output
            csv_file = self.ns3_path / "examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv"
            csv_content = ""
            if csv_file.exists():
                with open(csv_file, 'r') as f:
                    csv_content = f.read()
            
            duration = time.time() - start_time
            
            return {
                'success': True,
                'log_content': log_content,
                'csv_content': csv_content,
                'feedback_content': None,
                'stderr': stderr_content,
                'run_id': run_id,
                'duration': duration,
                'error': None
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                'success': False,
                'log_content': '',
                'feedback_content': None,
                'stderr': str(e),
                'run_id': run_id,
                'duration': duration,
                'error': str(e)
            }
    
    def _generate_run_id(self) -> str:
        """
        Generate unique run ID.
        
        Returns:
            Run ID string (timestamp-based)
        """
        return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    def _translate_to_cpp_format(self, test_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Translate Python test_inputs into the flat JSON the C++ simulator expects."""
        vl_id = test_inputs.get('vl_id', 0)
        metadata = test_inputs.get('metadata', {})
        
        # payload_delta_bytes: C++ applies base + delta, where base = (min+max)/2
        payload_delta = 0
        frame_size = metadata.get('frame_size')
        if frame_size and vl_id in self.vl_configs:
            base = self.vl_configs[vl_id]['base_size']
            payload_delta = int(frame_size) - base
        
        timing_jitter = metadata.get('timing_jitter_ms') or 0
        
        # BAG violation: if a non-standard bag_value is specified, express it as
        # negative jitter so the C++ traffic generator sends frames faster than BAG
        bag_value = metadata.get('bag_value')
        if bag_value and vl_id in self.vl_configs and timing_jitter == 0:
            normal_bag = self.vl_configs[vl_id]['bag_ms']
            if int(bag_value) < normal_bag:
                timing_jitter = int(bag_value) - normal_bag
        
        mutation_type = metadata.get('mutation_type', '')
        mac_mutation = "none"
        if mutation_type in ('mac_address', 'mac_spoofing', 'mac'):
            mac_mutation = "spoof_src"
        
        strategy_type = metadata.get('strategy_type', '')
        is_extreme = strategy_type in ('adversarial', 'edge-case')
        
        return {
            "vlId": vl_id,
            "prob": 1.0,
            "payload_delta_bytes": payload_delta,
            "timing_jitter_ms": int(timing_jitter),
            "mac_mutation": mac_mutation,
            "is_extreme_test": is_extreme,
        }
    
    def _write_mutations_file(self, test_inputs: Dict[str, Any]):
        """Translate test_inputs and write C++-compatible mutations.json."""
        cpp_mutations = self._translate_to_cpp_format(test_inputs)
        with open(self.mutations_file, 'w') as f:
            json.dump(cpp_mutations, f, indent=2)
    
    def _execute_ns3(
        self,
        scenario_name: str,
        timeout: int
    ) -> tuple[str, str]:
        """
        Execute ns-3 simulation.
        
        Args:
            scenario_name: Scenario to run
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (stdout, stderr)
        """
        # Build command
        cmd = [
            str(self.ns3_script),
            "run",
            scenario_name,
            "--no-build"  # Assume already built
        ]
        
        # Execute
        result = subprocess.run(
            cmd,
            cwd=str(self.ns3_path),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result.stdout, result.stderr
    
    def cleanup_old_files(self, days: int = 7):
        """
        Clean up old files from output directory.
        
        Args:
            days: Remove files older than this many days
        """
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        for filepath in self.output_dir.glob('*'):
            if filepath.is_file():
                if filepath.stat().st_mtime < cutoff_time:
                    filepath.unlink()
    
    def get_simulator_info(self) -> Dict[str, Any]:
        """
        Get information about ns-3 simulator.
        
        Returns:
            Dictionary with simulator info
        """
        return {
            'ns3_path': str(self.ns3_path),
            'ns3_exists': self.ns3_script.exists(),
            'mutations_file': str(self.mutations_file),
            'mutations_file_exists': self.mutations_file.exists(),
            'output_dir': str(self.output_dir),
            'output_files_count': len(list(self.output_dir.glob('*')))
        }


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("SIMULATOR RUNNER TEST")
    print("=" * 70)
    
    try:
        runner = SimulatorRunner()
        print("✓ Runner initialized")
        
        # Show info
        info = runner.get_simulator_info()
        print("\nSimulator info:")
        for key, value in info.items():
            print(f"  {key}: {value}")
        
        # Test mutations file creation (without actually running)
        print("\nTest: Write mutations.json (translation to C++ format)")
        test_inputs = {
            'vl_id': 2001,
            'frames': [],
            'metadata': {
                'mutation_type': 'bag',
                'bag_value': 3,
                'frame_size': None,
                'timing_jitter_ms': None,
                'strategy_type': 'edge-case',
            }
        }
        
        cpp_out = runner._translate_to_cpp_format(test_inputs)
        print(f"  Python input:  vl_id=2001, bag_value=3")
        print(f"  C++ output:    {json.dumps(cpp_out)}")
        runner._write_mutations_file(test_inputs)
        print(f"  Written to: {runner.mutations_file}")
        
        with open(runner.mutations_file, 'r') as f:
            print(f"  File content: {f.read()}")
        
        print("  ✓ Test passed")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

