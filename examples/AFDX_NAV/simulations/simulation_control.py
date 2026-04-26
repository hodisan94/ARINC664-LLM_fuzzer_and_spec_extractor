#!/usr/bin/env python3
"""
AFDX Simulation Control
=======================
Runs NS-3 AFDX simulations and analyzes the resulting PCAP files.

Features:
- Run specific simulations or all available simulations
- Automatic PCAP file discovery
- Integrated analysis with pcap_data_analyzer.py
- Comprehensive report generation

Usage:
    python simulation_control.py run <simulation_name> [options]
    python simulation_control.py analyze <pcap_file> [options]
    python simulation_control.py list
    python simulation_control.py --help
"""

import argparse
import os
import sys
import subprocess
import glob
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Import the analyzer
try:
    from pcap_data_analyzer import PcapAnalyzer, generate_text_report, generate_csv_report
except ImportError:
    # Handle case where script is run from different directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from pcap_data_analyzer import PcapAnalyzer, generate_text_report, generate_csv_report


class SimulationConfig:
    """Configuration for simulation runs"""
    
    def __init__(self):
        # Detect paths
        self.script_dir = Path(__file__).parent.absolute()
        self.afdx_dir = self.script_dir.parent
        self.ns3_root = self.afdx_dir.parent.parent
        
        # Output directories
        self.output_dir = self.afdx_dir / "output"
        self.pcap_dir = self.output_dir / "pcap"
        self.report_dir = self.output_dir / "reports"
        
        # NS-3 executable
        self.ns3_script = self.ns3_root / "ns3"
        
        # Known simulations
        self.simulations = {
            'afdx-nav-app-simulation': {
                'name': 'Navigation Application Simulation',
                'description': 'GPS receiver transmitting navigation data via AFDX',
                'pcap_pattern': 'nav-app/*.pcap',
                'default_args': [],
            },
            'afdx-demo': {
                'name': 'AFDX Demo Simulation',
                'description': 'Basic AFDX network demonstration',
                'pcap_pattern': 'demo/*.pcap',
                'default_args': [],
            },
        }
        
    def ensure_directories(self):
        """Create output directories if they don't exist"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pcap_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        
    def get_simulation_info(self, sim_name: str) -> Optional[Dict]:
        """Get information about a simulation"""
        return self.simulations.get(sim_name)
        
    def list_simulations(self) -> List[str]:
        """List available simulations"""
        return list(self.simulations.keys())
        
    def find_pcap_files(self, pattern: str = "**/*.pcap") -> List[Path]:
        """Find PCAP files matching pattern"""
        return list(self.pcap_dir.glob(pattern))


class SimulationRunner:
    """Handles running NS-3 simulations"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        
    def run_simulation(self, sim_name: str, args: List[str] = None,
                      verbose: bool = True) -> Tuple[bool, str]:
        """Run a simulation
        
        Args:
            sim_name: Name of simulation to run
            args: Additional command-line arguments
            verbose: Print output in real-time
            
        Returns:
            Tuple of (success, output_text)
        """
        
        if not self.config.ns3_script.exists():
            return False, f"NS-3 script not found: {self.config.ns3_script}"
            
        # Build command
        cmd = [str(self.config.ns3_script), "run", sim_name]
        
        if args:
            cmd.append("--")
            cmd.extend(args)
            
        if verbose:
            print(f"\n{'='*60}")
            print(f"Running: {' '.join(cmd)}")
            print(f"Working directory: {self.config.ns3_root}")
            print(f"{'='*60}\n")
            
        try:
            # Run simulation
            start_time = time.time()
            
            if verbose:
                # Stream output in real-time
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.config.ns3_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                output_lines = []
                for line in process.stdout:
                    print(line, end='')
                    output_lines.append(line)
                    
                process.wait()
                output = ''.join(output_lines)
                returncode = process.returncode
            else:
                result = subprocess.run(
                    cmd,
                    cwd=str(self.config.ns3_root),
                    capture_output=True,
                    text=True
                )
                output = result.stdout + result.stderr
                returncode = result.returncode
                
            elapsed = time.time() - start_time
            
            if verbose:
                print(f"\n{'='*60}")
                print(f"Simulation completed in {elapsed:.2f} seconds")
                print(f"Exit code: {returncode}")
                print(f"{'='*60}\n")
                
            return returncode == 0, output
            
        except Exception as e:
            return False, f"Error running simulation: {e}"
            
    def build_simulation(self, sim_name: str, verbose: bool = True) -> bool:
        """Build a specific simulation target"""
        
        cmd = [str(self.config.ns3_script), "build", sim_name]
        
        if verbose:
            print(f"Building {sim_name}...")
            
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.config.ns3_root),
                capture_output=not verbose,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Build error: {e}")
            return False


class AnalysisRunner:
    """Handles PCAP analysis"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        
    def analyze_pcap(self, pcap_path: Path, 
                     output_report: Path = None,
                     output_csv: Path = None,
                     verbose: bool = True) -> bool:
        """Analyze a single PCAP file
        
        Args:
            pcap_path: Path to PCAP file
            output_report: Path to save text report
            output_csv: Path to save CSV data
            verbose: Print report to console
            
        Returns:
            True if analysis succeeded
        """
        
        if not pcap_path.exists():
            print(f"Error: PCAP file not found: {pcap_path}")
            return False
            
        try:
            analyzer = PcapAnalyzer(str(pcap_path))
            report = analyzer.analyze()
            
            # Generate text report
            text_report = generate_text_report(report)
            
            if verbose:
                print(text_report)
                
            if output_report:
                output_report.parent.mkdir(parents=True, exist_ok=True)
                with open(output_report, 'w') as f:
                    f.write(text_report)
                print(f"\nReport saved to: {output_report}")
                
            if output_csv:
                output_csv.parent.mkdir(parents=True, exist_ok=True)
                csv_report = generate_csv_report(report)
                with open(output_csv, 'w') as f:
                    f.write(csv_report)
                print(f"CSV saved to: {output_csv}")
                
            return True
            
        except Exception as e:
            print(f"Error analyzing PCAP: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def analyze_all_pcaps(self, pattern: str = "**/*.pcap",
                          verbose: bool = True) -> Dict[str, bool]:
        """Analyze all PCAP files matching pattern
        
        Returns:
            Dict mapping pcap filename to success status
        """
        
        pcap_files = self.config.find_pcap_files(pattern)
        
        if not pcap_files:
            print(f"No PCAP files found matching: {pattern}")
            return {}
            
        results = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for pcap_path in pcap_files:
            rel_path = pcap_path.relative_to(self.config.pcap_dir)
            report_name = f"{rel_path.stem}_report_{timestamp}.txt"
            csv_name = f"{rel_path.stem}_data_{timestamp}.csv"
            
            report_path = self.config.report_dir / rel_path.parent / report_name
            csv_path = self.config.report_dir / rel_path.parent / csv_name
            
            print(f"\n{'#'*60}")
            print(f"Analyzing: {rel_path}")
            print(f"{'#'*60}")
            
            success = self.analyze_pcap(
                pcap_path,
                output_report=report_path,
                output_csv=csv_path,
                verbose=verbose
            )
            
            results[str(rel_path)] = success
            
        return results


class SimulationControl:
    """Main simulation control interface"""
    
    def __init__(self):
        self.config = SimulationConfig()
        self.runner = SimulationRunner(self.config)
        self.analyzer = AnalysisRunner(self.config)
        
    def run(self, sim_name: str, args: List[str] = None,
            analyze: bool = True, verbose: bool = True) -> bool:
        """Run a simulation and optionally analyze results
        
        Args:
            sim_name: Simulation name
            args: Additional arguments
            analyze: Run analysis after simulation
            verbose: Verbose output
            
        Returns:
            True if successful
        """
        
        self.config.ensure_directories()
        
        # Get simulation info
        sim_info = self.config.get_simulation_info(sim_name)
        
        if sim_info:
            print(f"\nSimulation: {sim_info['name']}")
            print(f"Description: {sim_info['description']}")
            
            # Merge default args
            if args is None:
                args = sim_info.get('default_args', [])
                
        # Run simulation
        success, output = self.runner.run_simulation(sim_name, args, verbose)
        
        if not success:
            print(f"\nSimulation failed!")
            return False
            
        # Analyze results
        if analyze:
            print("\n" + "="*60)
            print("ANALYZING SIMULATION RESULTS")
            print("="*60)
            
            # Find PCAP files
            if sim_info and 'pcap_pattern' in sim_info:
                pattern = sim_info['pcap_pattern']
            else:
                pattern = "**/*.pcap"
                
            # Wait briefly for files to be written
            time.sleep(0.5)
            
            results = self.analyzer.analyze_all_pcaps(pattern, verbose)
            
            if results:
                print("\n" + "="*60)
                print("ANALYSIS SUMMARY")
                print("="*60)
                for pcap, status in results.items():
                    status_str = "✅ SUCCESS" if status else "❌ FAILED"
                    print(f"  {pcap}: {status_str}")
                    
        return True
        
    def analyze(self, pcap_path: str, output: str = None,
                csv: str = None, verbose: bool = True) -> bool:
        """Analyze a specific PCAP file
        
        Args:
            pcap_path: Path to PCAP file
            output: Output report path
            csv: Output CSV path
            verbose: Verbose output
            
        Returns:
            True if successful
        """
        
        self.config.ensure_directories()
        
        pcap = Path(pcap_path)
        
        # Handle relative paths from PCAP directory
        if not pcap.is_absolute():
            pcap = self.config.pcap_dir / pcap
            
        output_path = Path(output) if output else None
        csv_path = Path(csv) if csv else None
        
        return self.analyzer.analyze_pcap(pcap, output_path, csv_path, verbose)
        
    def list_available(self):
        """List available simulations and PCAP files"""
        
        print("\n" + "="*60)
        print("AVAILABLE SIMULATIONS")
        print("="*60)
        
        for sim_name, info in self.config.simulations.items():
            print(f"\n  {sim_name}")
            print(f"    Name: {info['name']}")
            print(f"    Description: {info['description']}")
            
        print("\n" + "="*60)
        print("EXISTING PCAP FILES")
        print("="*60)
        
        pcap_files = self.config.find_pcap_files()
        
        if pcap_files:
            for pcap in sorted(pcap_files):
                rel_path = pcap.relative_to(self.config.pcap_dir)
                size = pcap.stat().st_size
                print(f"  {rel_path} ({size} bytes)")
        else:
            print("  No PCAP files found")
            
        print()


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="AFDX Simulation Control - Run and analyze NS-3 simulations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run       Run a simulation and analyze results
  analyze   Analyze existing PCAP files
  list      List available simulations and PCAP files

Examples:
  %(prog)s run afdx-nav-app-simulation
  %(prog)s run afdx-nav-app-simulation --no-analyze
  %(prog)s analyze nav-app/afdx-nav-app-0-0.pcap
  %(prog)s analyze nav-app/afdx-nav-app-0-0.pcap -o report.txt -c data.csv
  %(prog)s list
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run a simulation')
    run_parser.add_argument('simulation', help='Simulation name')
    run_parser.add_argument('--args', '-a', nargs='*', default=[],
                           help='Additional arguments to pass to simulation')
    run_parser.add_argument('--no-analyze', action='store_true',
                           help='Skip analysis after simulation')
    run_parser.add_argument('--quiet', '-q', action='store_true',
                           help='Suppress verbose output')
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze PCAP files')
    analyze_parser.add_argument('pcap', help='PCAP file to analyze')
    analyze_parser.add_argument('--output', '-o', help='Output report file')
    analyze_parser.add_argument('--csv', '-c', help='Output CSV file')
    analyze_parser.add_argument('--quiet', '-q', action='store_true',
                               help='Suppress verbose output')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available items')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
        
    control = SimulationControl()
    
    try:
        if args.command == 'run':
            success = control.run(
                args.simulation,
                args=args.args if args.args else None,
                analyze=not args.no_analyze,
                verbose=not args.quiet
            )
            return 0 if success else 1
            
        elif args.command == 'analyze':
            success = control.analyze(
                args.pcap,
                output=args.output,
                csv=args.csv,
                verbose=not args.quiet
            )
            return 0 if success else 1
            
        elif args.command == 'list':
            control.list_available()
            return 0
            
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
        
    return 0


if __name__ == '__main__':
    sys.exit(main())
