#!/usr/bin/env python3
"""
Simulator Runner

Executes the ns-3 AFDX simulator with generated test frames and collects results.
This is the bridge between the test generator and the simulator.
"""

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
    1. Write test frames to input file
    2. Execute ns-3 simulation
    3. Collect output logs
    4. Clean up temporary files
    5. Return results
    """
    
    def __init__(
        self,
        ns3_path: str = "/home/hodisan1994/ns-3-reset/ns-3",
        mutations_file: str = "examples/AFDX_V3/mutations.json",
        output_dir: str = "examples/AFDX_V3/output",
        skip_ns3_check: bool = False
    ):
        """
        Initialize simulator runner.
        
        Args:
            ns3_path: Path to ns-3 root directory
            mutations_file: Path to mutations.json file (relative to ns3_path)
            output_dir: Directory for simulator output
            skip_ns3_check: Skip verification of ns3 script (for testing)
        """
        self.ns3_path = Path(ns3_path)
        self.mutations_file = self.ns3_path / mutations_file
        self.output_dir = self.ns3_path / output_dir
        
        # Create directories
        self.mutations_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify ns3 executable exists
        self.ns3_script = self.ns3_path / "ns3"
        if not skip_ns3_check and not self.ns3_script.exists():
            raise FileNotFoundError(f"ns3 script not found: {self.ns3_script}")
    
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
    
    def _write_mutations_file(self, test_inputs: Dict[str, Any]):
        """
        Write test inputs to mutations.json file.
        
        Args:
            test_inputs: Test inputs dictionary from test generator
        """
        with open(self.mutations_file, 'w') as f:
            json.dump(test_inputs, f, indent=2)
    
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
        print("\nTest: Write mutations.json")
        test_inputs = {
            'vl_id': 2001,
            'frames': [
                {'time': 0.0, 'sequence_number': 1, 'bag_ms': 8, 'payload_hex': 'AABBCCDD'}
            ],
            'metadata': {'test': 'demo'}
        }
        
        runner._write_mutations_file(test_inputs)
        print(f"  Written to: {runner.mutations_file}")
        print(f"  Exists: {runner.mutations_file.exists()}")
        
        print("  ✓ Test passed")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

