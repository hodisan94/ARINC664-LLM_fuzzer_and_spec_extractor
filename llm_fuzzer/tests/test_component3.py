#!/usr/bin/env python3
"""
Unit tests for Component 3: Strategy-Driven Test Input Generator

Tests for:
- Custom Mutation Parser (mutation_parser.py)
- Test Generator (test_generator.py)
- Simulator Runner (simulator_runner.py)

Run with: python3 llm_fuzzer/tests/test_component3.py
Or: python3 -m pytest llm_fuzzer/tests/test_component3.py -v
"""

import sys
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.core.mutation_parser import CustomMutationParser
from llm_fuzzer.core.test_generator import TestGenerator
from llm_fuzzer.utils.simulator_runner import SimulatorRunner


class TestCustomMutationParser(unittest.TestCase):
    """Test cases for CustomMutationParser"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.parser = CustomMutationParser()
    
    def test_parse_bag_mutation(self):
        """Test parsing BAG mutations"""
        result = self.parser.parse("Set BAG to 5ms")
        self.assertEqual(result['bag_ms'], 5)
    
    def test_parse_frame_size_mutation(self):
        """Test parsing frame size mutations"""
        result = self.parser.parse("Frame size to 2000 bytes")
        self.assertEqual(result['frame_size'], 2000)
    
    def test_parse_vl_id_mutation(self):
        """Test parsing VL ID mutations"""
        result = self.parser.parse("Use VL ID 9999")
        self.assertEqual(result['vl_id'], 9999)
    
    def test_parse_combined_mutations(self):
        """Test parsing combined mutations"""
        result = self.parser.parse("Set BAG to 5ms AND frame size to 2000 bytes")
        self.assertEqual(result['bag_ms'], 5)
        self.assertEqual(result['frame_size'], 2000)
    
    def test_parse_with_vl_id_and_bag(self):
        """Test parsing complex mutation with multiple parameters"""
        result = self.parser.parse("VL 2001 with BAG 3ms and frame size 1519 bytes")
        self.assertEqual(result['vl_id'], 2001)
        self.assertEqual(result['bag_ms'], 3)
        self.assertEqual(result['frame_size'], 1519)
    
    def test_parse_sequence_number(self):
        """Test parsing sequence number mutations"""
        result = self.parser.parse("sequence starting from 100")
        self.assertEqual(result['sequence_number'], 100)
    
    def test_parse_invalid_sequence_flag(self):
        """Test parsing invalid sequence flag"""
        result = self.parser.parse("Invalid sequence numbers")
        self.assertTrue(result.get('invalid_sequence'))
    
    def test_parse_empty_string(self):
        """Test parsing empty string"""
        result = self.parser.parse("")
        self.assertEqual(result, {})
    
    def test_to_string_conversion(self):
        """Test converting mutations back to string"""
        mutations = {'bag_ms': 5, 'frame_size': 2000}
        result = self.parser.to_string(mutations)
        self.assertIn('BAG=5ms', result)
        self.assertIn('frame_size=2000 bytes', result)


class TestTestGenerator(unittest.TestCase):
    """Test cases for TestGenerator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.generator = TestGenerator()
    
    def test_initialization(self):
        """Test generator initializes correctly"""
        self.assertIsNotNone(self.generator.seed_frames)
        self.assertIsNotNone(self.generator.test_case_loader)
        self.assertIsNotNone(self.generator.mutation_parser)
    
    def test_load_seed_frame_existing_vl(self):
        """Test loading seed frame for existing VL"""
        seed = self.generator._load_seed_frame(2001)
        self.assertEqual(seed['vl_id'], 2001)
        self.assertIn('default_bag_ms', seed)
    
    def test_load_seed_frame_nonexistent_vl(self):
        """Test loading seed frame for non-existent VL (should use default)"""
        seed = self.generator._load_seed_frame(9999)
        self.assertEqual(seed['vl_id'], 9999)
        self.assertIn('default_bag_ms', seed)
    
    def test_generate_predefined_frames(self):
        """Test generating frames with predefined test cases"""
        strategy = {
            'target_vl': 2001,
            'protocol_rule': 'bag',
            'test_mode': 'predefined',
            'test_cases': ['TC0'],
            'custom_mutation': None,
            'strategy': 'edge-case'
        }
        
        result = self.generator.generate_test_inputs(strategy)
        
        self.assertEqual(result['vl_id'], 2001)
        self.assertGreater(len(result['frames']), 0)
        self.assertEqual(result['metadata']['test_mode'], 'predefined')
        
        # Check first frame has mutation applied (TC0 = BAG=0)
        first_frame = result['frames'][0]
        self.assertEqual(first_frame['bag_ms'], 0)
    
    def test_generate_custom_frames(self):
        """Test generating frames with custom mutation"""
        strategy = {
            'target_vl': 2001,
            'protocol_rule': 'bag',
            'test_mode': 'custom',
            'test_cases': None,
            'custom_mutation': 'Set BAG to 5ms',
            'strategy': 'adversarial'
        }
        
        result = self.generator.generate_test_inputs(strategy)
        
        self.assertEqual(result['vl_id'], 2001)
        self.assertGreater(len(result['frames']), 0)
        self.assertEqual(result['metadata']['test_mode'], 'custom')
        
        # Check mutation was applied
        first_frame = result['frames'][0]
        self.assertEqual(first_frame['bag_ms'], 5)
    
    def test_generate_custom_frames_combined(self):
        """Test generating frames with combined custom mutations"""
        strategy = {
            'target_vl': 2001,
            'protocol_rule': 'bag',
            'test_mode': 'custom',
            'test_cases': None,
            'custom_mutation': 'Set BAG to 5ms AND frame size to 2000 bytes',
            'strategy': 'adversarial'
        }
        
        result = self.generator.generate_test_inputs(strategy)
        
        first_frame = result['frames'][0]
        self.assertEqual(first_frame['bag_ms'], 5)
        # Frame size affects payload length
        # 2000 bytes = 4000 hex chars
        self.assertEqual(len(first_frame['payload_hex']), 4000)
    
    def test_create_frame_sequence_timing(self):
        """Test frame sequence timing is correct"""
        frames = self.generator._create_frame_sequence(
            vl_id=2001,
            bag_ms=8,
            frame_size=128,
            sequence_start=1,
            payload_hex='AABBCCDD',
            num_frames=5
        )
        
        self.assertEqual(len(frames), 5)
        
        # Check timing (BAG=8ms = 0.008s intervals)
        self.assertAlmostEqual(frames[0]['time'], 0.0)
        self.assertAlmostEqual(frames[1]['time'], 0.008, places=4)
        self.assertAlmostEqual(frames[2]['time'], 0.016, places=4)
    
    def test_create_frame_sequence_with_invalid_bag(self):
        """Test frame sequence with invalid BAG (0 or negative)"""
        frames = self.generator._create_frame_sequence(
            vl_id=2001,
            bag_ms=0,  # Invalid BAG
            frame_size=128,
            sequence_start=1,
            payload_hex='AABBCCDD',
            num_frames=3
        )
        
        self.assertEqual(len(frames), 3)
        # Should still generate frames with small intervals
        self.assertEqual(frames[0]['bag_ms'], 0)
        self.assertGreater(frames[1]['time'], 0)
    
    def test_serialize_to_json(self):
        """Test JSON serialization"""
        test_inputs = {
            'vl_id': 2001,
            'frames': [{'time': 0.0, 'seq': 1, 'bag_ms': 8, 'payload_hex': 'AABB'}],
            'metadata': {}
        }
        
        json_str = self.generator.serialize_to_json(test_inputs)
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed['vl_id'], 2001)
    
    def test_save_to_file(self):
        """Test saving to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_inputs = {
                'vl_id': 2001,
                'frames': [],
                'metadata': {}
            }
            
            output_path = Path(tmpdir) / "test_output.json"
            saved_path = self.generator.save_to_file(test_inputs, str(output_path))
            
            self.assertTrue(Path(saved_path).exists())
            
            # Verify content
            with open(saved_path, 'r') as f:
                loaded = json.load(f)
            self.assertEqual(loaded['vl_id'], 2001)


class TestSimulatorRunner(unittest.TestCase):
    """Test cases for SimulatorRunner"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temp directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.runner = SimulatorRunner(ns3_path=self.temp_dir, skip_ns3_check=True)
    
    def tearDown(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test runner initializes correctly"""
        self.assertTrue(self.runner.input_dir.exists())
        self.assertTrue(self.runner.output_dir.exists())
        self.assertTrue(self.runner.archive_dir.exists())
    
    def test_generate_run_id(self):
        """Test run ID generation"""
        run_id1 = self.runner._generate_run_id()
        run_id2 = self.runner._generate_run_id()
        
        self.assertIsNotNone(run_id1)
        self.assertIsNotNone(run_id2)
        self.assertNotEqual(run_id1, run_id2)  # Should be unique
    
    def test_write_input_file(self):
        """Test writing input file"""
        test_inputs = {
            'vl_id': 2001,
            'frames': [{'time': 0.0, 'seq': 1, 'bag_ms': 8, 'payload_hex': 'AABB'}],
            'metadata': {}
        }
        
        run_id = "test_run"
        filepath = self.runner._write_input_file(test_inputs, run_id)
        
        self.assertTrue(filepath.exists())
        self.assertEqual(filepath.name, "test_run.json")
        
        # Verify content
        with open(filepath, 'r') as f:
            loaded = json.load(f)
        self.assertEqual(loaded['vl_id'], 2001)
    
    def test_get_simulator_info(self):
        """Test getting simulator info"""
        info = self.runner.get_simulator_info()
        
        self.assertIn('ns3_path', info)
        self.assertIn('input_dir', info)
        self.assertIn('output_dir', info)
        self.assertIsInstance(info['input_files_count'], int)


def run_tests():
    """Run all tests"""
    print("=" * 70)
    print("RUNNING COMPONENT 3 TESTS")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestCustomMutationParser))
    suite.addTests(loader.loadTestsFromTestCase(TestTestGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestSimulatorRunner))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

