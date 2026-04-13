#!/usr/bin/env python3
"""
AFDX PCAP Data Analyzer
=======================
Analyzes PCAP files from AFDX simulations and generates comprehensive reports.

Supports decoding:
- AFDX frame headers (VL ID, Sequence Number)
- GPS message payloads (header, satellite data, CRC)
- Frame statistics and validation
- Comparison with simulation CSV log files

Usage:
    python pcap_data_analyzer.py <pcap_file> [--output <report_file>] [--csv <csv_file>]
    python pcap_data_analyzer.py <pcap_file> --compare <events_csv_file>
    python pcap_data_analyzer.py --help
"""

import struct
import argparse
import os
import sys
import csv
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import IntEnum


class FixType(IntEnum):
    """GPS Fix Type enumeration"""
    NO_FIX = 0
    FIX_2D = 1
    FIX_3D = 2


@dataclass
class SatelliteData:
    """Satellite/GPS position and velocity data"""
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    velocity_z: float = 0.0
    time_of_week: float = 0.0
    num_satellites: int = 0
    fix_type: int = 0

    def fix_type_str(self) -> str:
        """Get fix type as string"""
        names = {0: "NO_FIX", 1: "2D_FIX", 2: "3D_FIX"}
        return names.get(self.fix_type, "UNKNOWN")

    def is_valid_fix(self) -> bool:
        """Check if fix is valid (2D or 3D)"""
        return self.fix_type in (FixType.FIX_2D, FixType.FIX_3D)


@dataclass
class GpsMessage:
    """GPS Message structure"""
    message_id: int = 0
    gps_receiver_id: int = 0
    timestamp_ms: int = 0
    satellite_data: SatelliteData = field(default_factory=SatelliteData)
    checksum: int = 0
    checksum_valid: bool = False


@dataclass
class AfdxFrame:
    """AFDX Frame structure"""
    # Ethernet header (from PCAP)
    dst_mac: str = ""
    src_mac: str = ""
    ether_type: int = 0
    
    # AFDX sub-header
    vl_id: int = 0
    sequence_number: int = 0
    
    # Payload
    gps_message: Optional[GpsMessage] = None
    raw_payload: bytes = b""
    
    # Metadata
    timestamp: float = 0.0
    frame_length: int = 0
    packet_number: int = 0


@dataclass
class AnalysisReport:
    """Analysis report structure"""
    pcap_file: str = ""
    analysis_time: str = ""
    total_frames: int = 0
    valid_frames: int = 0
    invalid_frames: int = 0
    
    # VL statistics
    vl_stats: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # Sequence number tracking
    sequence_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # GPS data statistics
    gps_stats: Dict[str, Any] = field(default_factory=dict)
    
    # CRC statistics
    crc_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # All decoded frames
    frames: List[AfdxFrame] = field(default_factory=list)
    
    # CSV comparison results
    csv_comparison: Optional[Dict[str, Any]] = None


@dataclass
class CsvLogEntry:
    """Parsed CSV log entry"""
    timestamp: float = 0.0
    event: str = ""
    source: str = ""
    destination: str = ""
    vl_id: int = 0
    seq_num: int = 0
    network: str = ""
    frame_size: int = 0
    payload_size: int = 0
    
    # Parsed payload fields
    status: str = ""
    msg_id: int = 0
    gps_rx_id: int = 0
    gps_timestamp_ms: int = 0
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0
    tow: float = 0.0
    num_sats: int = 0
    fix_type: str = ""
    crc32: int = 0


class PcapReader:
    """Simple PCAP file reader"""
    
    PCAP_MAGIC_LE = 0xa1b2c3d4
    PCAP_MAGIC_BE = 0xd4c3b2a1
    PCAP_MAGIC_NS_LE = 0xa1b23c4d
    PCAP_MAGIC_NS_BE = 0x4d3cb2a1
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = None
        self.byte_order = '<'  # Little endian by default
        self.nanosecond_ts = False
        self.link_type = 0
        
    def __enter__(self):
        self.open()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def open(self):
        """Open PCAP file and read global header"""
        self.file = open(self.filepath, 'rb')
        self._read_global_header()
        
    def close(self):
        """Close PCAP file"""
        if self.file:
            self.file.close()
            self.file = None
            
    def _read_global_header(self):
        """Read and parse PCAP global header"""
        header = self.file.read(24)
        if len(header) < 24:
            raise ValueError("Invalid PCAP file: too short for global header")
            
        magic = struct.unpack('<I', header[0:4])[0]
        
        if magic == self.PCAP_MAGIC_LE:
            self.byte_order = '<'
            self.nanosecond_ts = False
        elif magic == self.PCAP_MAGIC_BE:
            self.byte_order = '>'
            self.nanosecond_ts = False
        elif magic == self.PCAP_MAGIC_NS_LE:
            self.byte_order = '<'
            self.nanosecond_ts = True
        elif magic == self.PCAP_MAGIC_NS_BE:
            self.byte_order = '>'
            self.nanosecond_ts = True
        else:
            raise ValueError(f"Invalid PCAP magic number: 0x{magic:08x}")
            
        # Parse rest of header
        fmt = f'{self.byte_order}HHIIII'
        _, _, _, _, _, self.link_type = struct.unpack(fmt, header[4:24])
        
    def read_packet(self) -> Optional[Tuple[float, bytes]]:
        """Read next packet from PCAP file
        
        Returns:
            Tuple of (timestamp, packet_data) or None if EOF
        """
        # Read packet header (16 bytes)
        header = self.file.read(16)
        if len(header) < 16:
            return None
            
        fmt = f'{self.byte_order}IIII'
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(fmt, header)
        
        # Calculate timestamp
        if self.nanosecond_ts:
            timestamp = ts_sec + ts_usec / 1e9
        else:
            timestamp = ts_sec + ts_usec / 1e6
            
        # Read packet data
        data = self.file.read(incl_len)
        if len(data) < incl_len:
            return None
            
        return (timestamp, data)
        
    def __iter__(self):
        """Iterate over packets"""
        while True:
            packet = self.read_packet()
            if packet is None:
                break
            yield packet


class AfdxPayloadDecoder:
    """Decoder for AFDX GPS payload data"""
    
    # CRC-32 lookup table (IEEE 802.3 polynomial)
    CRC_TABLE = None
    
    @classmethod
    def _init_crc_table(cls):
        """Initialize CRC-32 lookup table"""
        if cls.CRC_TABLE is not None:
            return
            
        cls.CRC_TABLE = []
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xEDB88320
                else:
                    crc >>= 1
            cls.CRC_TABLE.append(crc)
    
    @classmethod
    def calculate_crc32(cls, data: bytes) -> int:
        """Calculate CRC-32 checksum"""
        cls._init_crc_table()
        crc = 0xFFFFFFFF
        for byte in data:
            crc = cls.CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
        return crc ^ 0xFFFFFFFF
    
    @staticmethod
    def decode_double_be(data: bytes, offset: int) -> float:
        """Decode big-endian double"""
        return struct.unpack('>d', data[offset:offset+8])[0]
    
    @staticmethod
    def decode_uint16_be(data: bytes, offset: int) -> int:
        """Decode big-endian uint16"""
        return struct.unpack('>H', data[offset:offset+2])[0]
    
    @staticmethod
    def decode_uint32_be(data: bytes, offset: int) -> int:
        """Decode big-endian uint32"""
        return struct.unpack('>I', data[offset:offset+4])[0]
    
    @classmethod
    def decode_satellite_data(cls, data: bytes, offset: int) -> SatelliteData:
        """Decode satellite data from payload"""
        sat = SatelliteData()
        
        sat.position_x = cls.decode_double_be(data, offset)
        sat.position_y = cls.decode_double_be(data, offset + 8)
        sat.position_z = cls.decode_double_be(data, offset + 16)
        sat.velocity_x = cls.decode_double_be(data, offset + 24)
        sat.velocity_y = cls.decode_double_be(data, offset + 32)
        sat.velocity_z = cls.decode_double_be(data, offset + 40)
        sat.time_of_week = cls.decode_double_be(data, offset + 48)
        sat.num_satellites = data[offset + 56]
        sat.fix_type = data[offset + 57]
        
        return sat
    
    @classmethod
    def decode_gps_message(cls, data: bytes, offset: int = 0) -> GpsMessage:
        """Decode GPS message from payload
        
        Expected structure (72 bytes):
        - Header (8 bytes): message_id(2), gps_receiver_id(2), timestamp_ms(4)
        - Satellite data (58 bytes)
        - Checksum (4 bytes)
        - Padding (2 bytes)
        """
        msg = GpsMessage()
        
        # Header
        msg.message_id = cls.decode_uint16_be(data, offset)
        msg.gps_receiver_id = cls.decode_uint16_be(data, offset + 2)
        msg.timestamp_ms = cls.decode_uint32_be(data, offset + 4)
        
        # Satellite data
        msg.satellite_data = cls.decode_satellite_data(data, offset + 8)
        
        # Checksum
        msg.checksum = cls.decode_uint32_be(data, offset + 66)
        
        # Verify checksum
        msg_data = data[offset:offset + 66]  # Header + satellite data
        calculated_crc = cls.calculate_crc32(msg_data)
        msg.checksum_valid = (calculated_crc == msg.checksum)
        
        return msg
    
    @classmethod
    def decode_afdx_payload(cls, data: bytes) -> Tuple[int, int, Optional[GpsMessage]]:
        """Decode AFDX payload (after Ethernet header)
        
        Expected structure:
        - VL ID (2 bytes, big-endian)
        - Sequence Number (1 byte)
        - Padding (1 byte)
        - GPS Message (72 bytes)
        
        Returns:
            Tuple of (vl_id, sequence_number, gps_message)
        """
        if len(data) < 4:
            return 0, 0, None
            
        vl_id = cls.decode_uint16_be(data, 0)
        seq_num = data[2]
        
        gps_msg = None
        if len(data) >= 76:  # 4 + 72 bytes
            gps_msg = cls.decode_gps_message(data, 4)
            
        return vl_id, seq_num, gps_msg


class PcapAnalyzer:
    """Main PCAP analyzer class"""
    
    ETHER_TYPE_AFDX = 0x88B5
    
    def __init__(self, pcap_file: str):
        self.pcap_file = pcap_file
        self.report = AnalysisReport()
        self.report.pcap_file = pcap_file
        self.report.analysis_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Track sequence numbers per VL
        self.last_seq: Dict[int, int] = {}
        
    def analyze(self) -> AnalysisReport:
        """Analyze PCAP file and generate report"""
        
        if not os.path.exists(self.pcap_file):
            raise FileNotFoundError(f"PCAP file not found: {self.pcap_file}")
            
        packet_num = 0
        
        with PcapReader(self.pcap_file) as reader:
            for timestamp, packet_data in reader:
                packet_num += 1
                frame = self._decode_frame(packet_num, timestamp, packet_data)
                
                if frame:
                    self.report.frames.append(frame)
                    self._update_statistics(frame)
                    self.report.valid_frames += 1
                else:
                    self.report.invalid_frames += 1
                    
        self.report.total_frames = packet_num
        self._finalize_statistics()
        
        return self.report
    
    def _decode_frame(self, packet_num: int, timestamp: float, 
                      data: bytes) -> Optional[AfdxFrame]:
        """Decode a single Ethernet frame"""
        
        if len(data) < 14:  # Minimum Ethernet header
            return None
            
        frame = AfdxFrame()
        frame.packet_number = packet_num
        frame.timestamp = timestamp
        frame.frame_length = len(data)
        
        # Parse Ethernet header
        frame.dst_mac = ':'.join(f'{b:02x}' for b in data[0:6])
        frame.src_mac = ':'.join(f'{b:02x}' for b in data[6:12])
        frame.ether_type = struct.unpack('>H', data[12:14])[0]
        
        # Check if AFDX frame
        if frame.ether_type != self.ETHER_TYPE_AFDX:
            return None
            
        # Decode AFDX payload
        payload = data[14:]
        frame.raw_payload = payload
        
        vl_id, seq_num, gps_msg = AfdxPayloadDecoder.decode_afdx_payload(payload)
        frame.vl_id = vl_id
        frame.sequence_number = seq_num
        frame.gps_message = gps_msg
        
        return frame
    
    def _update_statistics(self, frame: AfdxFrame):
        """Update statistics with new frame"""
        
        vl_id = frame.vl_id
        
        # Initialize VL stats if needed
        if vl_id not in self.report.vl_stats:
            self.report.vl_stats[vl_id] = {
                'frame_count': 0,
                'first_timestamp': frame.timestamp,
                'last_timestamp': frame.timestamp,
                'total_bytes': 0,
                'crc_valid': 0,
                'crc_invalid': 0,
                'sequence_gaps': 0,
            }
            
        stats = self.report.vl_stats[vl_id]
        stats['frame_count'] += 1
        stats['last_timestamp'] = frame.timestamp
        stats['total_bytes'] += frame.frame_length
        
        # Check sequence number
        if vl_id in self.last_seq:
            expected_seq = (self.last_seq[vl_id] + 1) % 256
            if frame.sequence_number != expected_seq:
                stats['sequence_gaps'] += 1
                self.report.sequence_errors.append({
                    'packet': frame.packet_number,
                    'vl_id': vl_id,
                    'expected': expected_seq,
                    'received': frame.sequence_number,
                    'timestamp': frame.timestamp,
                })
        self.last_seq[vl_id] = frame.sequence_number
        
        # Check CRC
        if frame.gps_message:
            if frame.gps_message.checksum_valid:
                stats['crc_valid'] += 1
            else:
                stats['crc_invalid'] += 1
                self.report.crc_errors.append({
                    'packet': frame.packet_number,
                    'vl_id': vl_id,
                    'message_id': frame.gps_message.message_id,
                    'timestamp': frame.timestamp,
                })
                
    def _finalize_statistics(self):
        """Calculate final statistics"""
        
        # GPS statistics
        gps_frames = [f for f in self.report.frames if f.gps_message]
        
        if gps_frames:
            positions_x = [f.gps_message.satellite_data.position_x for f in gps_frames]
            positions_y = [f.gps_message.satellite_data.position_y for f in gps_frames]
            positions_z = [f.gps_message.satellite_data.position_z for f in gps_frames]
            
            self.report.gps_stats = {
                'total_messages': len(gps_frames),
                'position_x_range': (min(positions_x), max(positions_x)),
                'position_y_range': (min(positions_y), max(positions_y)),
                'position_z_range': (min(positions_z), max(positions_z)),
                'fix_types': {},
            }
            
            # Count fix types
            for f in gps_frames:
                fix = f.gps_message.satellite_data.fix_type_str()
                self.report.gps_stats['fix_types'][fix] = \
                    self.report.gps_stats['fix_types'].get(fix, 0) + 1
                    
        # Calculate rates for each VL
        for vl_id, stats in self.report.vl_stats.items():
            duration = stats['last_timestamp'] - stats['first_timestamp']
            if duration > 0:
                stats['frame_rate'] = stats['frame_count'] / duration
                stats['data_rate_bps'] = (stats['total_bytes'] * 8) / duration
            else:
                stats['frame_rate'] = 0
                stats['data_rate_bps'] = 0


class CsvLogParser:
    """Parser for simulation event CSV log files"""
    
    @staticmethod
    def parse_payload_field(payload_str: str) -> Dict[str, Any]:
        """Parse the payload field from CSV (semicolon-separated key=value pairs)"""
        result = {}
        
        if not payload_str:
            return result
            
        # Remove surrounding quotes if present
        payload_str = payload_str.strip('"')
        
        # Split by semicolon and parse each field
        for field in payload_str.split(';'):
            if '=' in field:
                key, value = field.split('=', 1)
                result[key] = value
                
        return result
    
    @classmethod
    def parse_csv_file(cls, csv_path: str, 
                       network_filter: str = None,
                       event_filter: str = None) -> List[CsvLogEntry]:
        """Parse CSV log file and return list of entries
        
        Args:
            csv_path: Path to CSV file
            network_filter: Filter by network (e.g., 'NET_A', 'NET_B')
            event_filter: Filter by event type (e.g., 'AFDX_TX', 'AFDX_RX')
            
        Returns:
            List of CsvLogEntry objects
        """
        entries = []
        
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Apply filters
                if network_filter and row.get('Network') != network_filter:
                    continue
                if event_filter and row.get('Event') != event_filter:
                    continue
                    
                entry = CsvLogEntry()
                
                # Parse basic fields
                entry.timestamp = float(row.get('Timestamp_s', 0))
                entry.event = row.get('Event', '')
                entry.source = row.get('Source', '')
                entry.destination = row.get('Destination', '')
                entry.vl_id = int(row.get('VL_ID', 0))
                entry.seq_num = int(row.get('SeqNum', 0))
                entry.network = row.get('Network', '')
                entry.frame_size = int(row.get('FrameSize_bytes', 0))
                entry.payload_size = int(row.get('PayloadSize_bytes', 0))
                
                # Parse payload fields
                payload_data = cls.parse_payload_field(row.get('Payload', ''))
                
                entry.status = payload_data.get('Status', '')
                entry.msg_id = int(payload_data.get('MsgID', 0))
                entry.gps_rx_id = int(payload_data.get('GPS_RxID', 0))
                entry.gps_timestamp_ms = int(payload_data.get('GPS_Timestamp_ms', 0))
                entry.pos_x = float(payload_data.get('Sat_PosX_m', 0))
                entry.pos_y = float(payload_data.get('Sat_PosY_m', 0))
                entry.pos_z = float(payload_data.get('Sat_PosZ_m', 0))
                entry.vel_x = float(payload_data.get('Sat_VelX_ms', 0))
                entry.vel_y = float(payload_data.get('Sat_VelY_ms', 0))
                entry.vel_z = float(payload_data.get('Sat_VelZ_ms', 0))
                entry.tow = float(payload_data.get('Sat_TOW_s', 0))
                entry.num_sats = int(payload_data.get('Sat_NumSats', 0))
                entry.fix_type = payload_data.get('Sat_FixType', '')
                
                # Parse CRC (hex string like "0xe37df7db")
                crc_str = payload_data.get('CRC32', '0')
                if crc_str.startswith('0x'):
                    entry.crc32 = int(crc_str, 16)
                else:
                    entry.crc32 = int(crc_str) if crc_str.isdigit() else 0
                    
                entries.append(entry)
                
        return entries


class PcapCsvComparator:
    """Compares PCAP decoded data with CSV log data"""
    
    # Tolerance for floating point comparisons
    FLOAT_TOLERANCE = 0.01
    
    def __init__(self, pcap_frames: List[AfdxFrame], csv_entries: List[CsvLogEntry]):
        self.pcap_frames = pcap_frames
        self.csv_entries = csv_entries
        
    def compare(self) -> Dict[str, Any]:
        """Compare PCAP frames with CSV entries
        
        Returns:
            Comparison result dictionary
        """
        result = {
            'total_pcap_frames': len(self.pcap_frames),
            'total_csv_entries': len(self.csv_entries),
            'matched_frames': 0,
            'mismatched_frames': 0,
            'unmatched_pcap': 0,
            'unmatched_csv': 0,
            'field_mismatches': [],
            'matches': [],
        }
        
        # Index CSV entries by (timestamp, vl_id, msg_id) for matching
        csv_index: Dict[Tuple, List[CsvLogEntry]] = {}
        for entry in self.csv_entries:
            key = (round(entry.timestamp, 3), entry.vl_id, entry.msg_id)
            if key not in csv_index:
                csv_index[key] = []
            csv_index[key].append(entry)
            
        used_csv_entries = set()
        
        for frame in self.pcap_frames:
            if not frame.gps_message:
                continue
                
            msg = frame.gps_message
            sat = msg.satellite_data
            
            # Try to find matching CSV entry
            key = (round(frame.timestamp, 3), frame.vl_id, msg.message_id)
            
            matched = False
            if key in csv_index:
                for i, csv_entry in enumerate(csv_index[key]):
                    entry_id = (key, i)
                    if entry_id in used_csv_entries:
                        continue
                        
                    # Compare fields
                    mismatches = self._compare_fields(frame, csv_entry)
                    
                    if not mismatches:
                        result['matched_frames'] += 1
                        result['matches'].append({
                            'pcap_packet': frame.packet_number,
                            'csv_timestamp': csv_entry.timestamp,
                            'msg_id': msg.message_id,
                            'status': 'MATCH',
                        })
                    else:
                        result['mismatched_frames'] += 1
                        result['field_mismatches'].append({
                            'pcap_packet': frame.packet_number,
                            'pcap_timestamp': frame.timestamp,
                            'csv_timestamp': csv_entry.timestamp,
                            'msg_id': msg.message_id,
                            'mismatches': mismatches,
                        })
                        
                    used_csv_entries.add(entry_id)
                    matched = True
                    break
                    
            if not matched:
                result['unmatched_pcap'] += 1
                
        # Count unmatched CSV entries
        total_csv_used = len(used_csv_entries)
        result['unmatched_csv'] = len(self.csv_entries) - total_csv_used
        
        # Calculate summary
        total_compared = result['matched_frames'] + result['mismatched_frames']
        if total_compared > 0:
            result['match_rate'] = result['matched_frames'] / total_compared * 100
        else:
            result['match_rate'] = 0
            
        return result
        
    def _compare_fields(self, frame: AfdxFrame, csv_entry: CsvLogEntry) -> List[Dict]:
        """Compare individual fields between PCAP frame and CSV entry
        
        Returns:
            List of mismatched fields
        """
        mismatches = []
        
        msg = frame.gps_message
        sat = msg.satellite_data
        
        # Define field comparisons: (name, pcap_value, csv_value, is_float)
        comparisons = [
            ('VL_ID', frame.vl_id, csv_entry.vl_id, False),
            ('MsgID', msg.message_id, csv_entry.msg_id, False),
            ('GPS_RxID', msg.gps_receiver_id, csv_entry.gps_rx_id, False),
            ('GPS_Timestamp_ms', msg.timestamp_ms, csv_entry.gps_timestamp_ms, False),
            ('Position_X', sat.position_x, csv_entry.pos_x, True),
            ('Position_Y', sat.position_y, csv_entry.pos_y, True),
            ('Position_Z', sat.position_z, csv_entry.pos_z, True),
            ('Velocity_X', sat.velocity_x, csv_entry.vel_x, True),
            ('Velocity_Y', sat.velocity_y, csv_entry.vel_y, True),
            ('Velocity_Z', sat.velocity_z, csv_entry.vel_z, True),
            ('TOW', sat.time_of_week, csv_entry.tow, True),
            ('NumSats', sat.num_satellites, csv_entry.num_sats, False),
            ('CRC32', msg.checksum, csv_entry.crc32, False),
        ]
        
        for name, pcap_val, csv_val, is_float in comparisons:
            if is_float:
                if abs(pcap_val - csv_val) > self.FLOAT_TOLERANCE:
                    mismatches.append({
                        'field': name,
                        'pcap_value': pcap_val,
                        'csv_value': csv_val,
                        'difference': abs(pcap_val - csv_val),
                    })
            else:
                if pcap_val != csv_val:
                    mismatches.append({
                        'field': name,
                        'pcap_value': pcap_val,
                        'csv_value': csv_val,
                    })
                    
        # Compare fix type (string vs int)
        fix_type_str = sat.fix_type_str()
        if fix_type_str != csv_entry.fix_type:
            mismatches.append({
                'field': 'FixType',
                'pcap_value': fix_type_str,
                'csv_value': csv_entry.fix_type,
            })
            
        return mismatches


def generate_text_report(report: AnalysisReport) -> str:
    """Generate human-readable text report"""
    
    lines = []
    lines.append("=" * 80)
    lines.append("AFDX PCAP ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"File:          {report.pcap_file}")
    lines.append(f"Analysis Time: {report.analysis_time}")
    lines.append("")
    
    # Frame summary
    lines.append("-" * 80)
    lines.append("FRAME SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Total Frames:   {report.total_frames}")
    lines.append(f"Valid Frames:   {report.valid_frames}")
    lines.append(f"Invalid Frames: {report.invalid_frames}")
    lines.append("")
    
    # VL Statistics
    lines.append("-" * 80)
    lines.append("VIRTUAL LINK STATISTICS")
    lines.append("-" * 80)
    
    for vl_id in sorted(report.vl_stats.keys()):
        stats = report.vl_stats[vl_id]
        lines.append(f"\nVL {vl_id}:")
        lines.append(f"  Frame Count:     {stats['frame_count']}")
        lines.append(f"  Total Bytes:     {stats['total_bytes']}")
        lines.append(f"  Frame Rate:      {stats['frame_rate']:.2f} fps")
        lines.append(f"  Data Rate:       {stats['data_rate_bps']/1000:.2f} kbps")
        lines.append(f"  CRC Valid:       {stats['crc_valid']}")
        lines.append(f"  CRC Invalid:     {stats['crc_invalid']}")
        lines.append(f"  Sequence Gaps:   {stats['sequence_gaps']}")
        
    # GPS Statistics
    if report.gps_stats:
        lines.append("")
        lines.append("-" * 80)
        lines.append("GPS DATA STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Total GPS Messages: {report.gps_stats['total_messages']}")
        lines.append(f"Position X Range:   {report.gps_stats['position_x_range'][0]:.2f} to {report.gps_stats['position_x_range'][1]:.2f} m")
        lines.append(f"Position Y Range:   {report.gps_stats['position_y_range'][0]:.2f} to {report.gps_stats['position_y_range'][1]:.2f} m")
        lines.append(f"Position Z Range:   {report.gps_stats['position_z_range'][0]:.2f} to {report.gps_stats['position_z_range'][1]:.2f} m")
        lines.append("Fix Types:")
        for fix, count in report.gps_stats['fix_types'].items():
            lines.append(f"  {fix}: {count}")
            
    # Errors
    if report.sequence_errors:
        lines.append("")
        lines.append("-" * 80)
        lines.append(f"SEQUENCE ERRORS ({len(report.sequence_errors)} total)")
        lines.append("-" * 80)
        for err in report.sequence_errors[:10]:  # Show first 10
            lines.append(f"  Packet {err['packet']}: VL {err['vl_id']} - "
                        f"Expected seq {err['expected']}, got {err['received']}")
        if len(report.sequence_errors) > 10:
            lines.append(f"  ... and {len(report.sequence_errors) - 10} more")
            
    if report.crc_errors:
        lines.append("")
        lines.append("-" * 80)
        lines.append(f"CRC ERRORS ({len(report.crc_errors)} total)")
        lines.append("-" * 80)
        for err in report.crc_errors[:10]:
            lines.append(f"  Packet {err['packet']}: VL {err['vl_id']}, "
                        f"MsgID {err['message_id']}")
        if len(report.crc_errors) > 10:
            lines.append(f"  ... and {len(report.crc_errors) - 10} more")
            
    # Frame details (first 5)
    lines.append("")
    lines.append("-" * 80)
    lines.append("FRAME DETAILS (first 5 frames)")
    lines.append("-" * 80)
    
    for frame in report.frames[:5]:
        lines.append(f"\nPacket #{frame.packet_number} @ {frame.timestamp:.6f}s")
        lines.append(f"  Src: {frame.src_mac} -> Dst: {frame.dst_mac}")
        lines.append(f"  VL ID: {frame.vl_id}, Seq: {frame.sequence_number}")
        
        if frame.gps_message:
            msg = frame.gps_message
            sat = msg.satellite_data
            lines.append(f"  GPS Message ID: {msg.message_id}, "
                        f"Rx ID: {msg.gps_receiver_id}, "
                        f"Timestamp: {msg.timestamp_ms} ms")
            lines.append(f"  Position: ({sat.position_x:.2f}, "
                        f"{sat.position_y:.2f}, {sat.position_z:.2f}) m")
            lines.append(f"  Velocity: ({sat.velocity_x:.2f}, "
                        f"{sat.velocity_y:.2f}, {sat.velocity_z:.2f}) m/s")
            lines.append(f"  TOW: {sat.time_of_week:.3f}s, "
                        f"Sats: {sat.num_satellites}, "
                        f"Fix: {sat.fix_type_str()}")
            lines.append(f"  CRC: 0x{msg.checksum:08x} "
                        f"({'VALID' if msg.checksum_valid else 'INVALID'})")
    
    # CSV Comparison Results
    if report.csv_comparison:
        lines.append("")
        lines.append("=" * 80)
        lines.append("CSV COMPARISON RESULTS")
        lines.append("=" * 80)
        
        comp = report.csv_comparison
        lines.append(f"PCAP Frames:        {comp['total_pcap_frames']}")
        lines.append(f"CSV Entries:        {comp['total_csv_entries']}")
        lines.append(f"Matched Frames:     {comp['matched_frames']}")
        lines.append(f"Mismatched Frames:  {comp['mismatched_frames']}")
        lines.append(f"Unmatched PCAP:     {comp['unmatched_pcap']}")
        lines.append(f"Unmatched CSV:      {comp['unmatched_csv']}")
        lines.append(f"Match Rate:         {comp['match_rate']:.1f}%")
        
        if comp['matched_frames'] > 0:
            lines.append("")
            lines.append("-" * 80)
            lines.append("MATCHED FRAMES")
            lines.append("-" * 80)
            for match in comp['matches'][:10]:
                lines.append(f"  ✅ Packet #{match['pcap_packet']}: "
                            f"MsgID={match['msg_id']} @ {match['csv_timestamp']:.6f}s")
            if len(comp['matches']) > 10:
                lines.append(f"  ... and {len(comp['matches']) - 10} more matches")
        
        if comp['field_mismatches']:
            lines.append("")
            lines.append("-" * 80)
            lines.append(f"FIELD MISMATCHES ({len(comp['field_mismatches'])} frames)")
            lines.append("-" * 80)
            
            for mismatch in comp['field_mismatches'][:10]:
                lines.append(f"\n  ❌ Packet #{mismatch['pcap_packet']} "
                            f"(MsgID={mismatch['msg_id']}):")
                lines.append(f"     PCAP timestamp: {mismatch['pcap_timestamp']:.6f}s")
                lines.append(f"     CSV timestamp:  {mismatch['csv_timestamp']:.6f}s")
                
                for field_mismatch in mismatch['mismatches']:
                    field = field_mismatch['field']
                    pcap_val = field_mismatch['pcap_value']
                    csv_val = field_mismatch['csv_value']
                    
                    if isinstance(pcap_val, float):
                        lines.append(f"     {field}: PCAP={pcap_val:.6f}, CSV={csv_val:.6f}")
                    elif field == 'CRC32':
                        lines.append(f"     {field}: PCAP=0x{pcap_val:08x}, CSV=0x{csv_val:08x}")
                    else:
                        lines.append(f"     {field}: PCAP={pcap_val}, CSV={csv_val}")
                        
            if len(comp['field_mismatches']) > 10:
                lines.append(f"\n  ... and {len(comp['field_mismatches']) - 10} more mismatches")
        
        # Overall comparison verdict
        lines.append("")
        lines.append("-" * 80)
        if comp['matched_frames'] > 0 and comp['mismatched_frames'] == 0:
            lines.append("✅ VERIFICATION PASSED: All compared frames match CSV data!")
        elif comp['mismatched_frames'] > 0:
            lines.append(f"⚠️  VERIFICATION WARNING: {comp['mismatched_frames']} frames have field mismatches")
        else:
            lines.append("⚠️  VERIFICATION INCOMPLETE: No frames could be matched")
        lines.append("-" * 80)
                        
    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)
    
    return '\n'.join(lines)


def generate_csv_report(report: AnalysisReport) -> str:
    """Generate CSV report of all frames"""
    
    lines = []
    
    # Header
    header = [
        "Packet", "Timestamp_s", "Src_MAC", "Dst_MAC", "VL_ID", "SeqNum",
        "MsgID", "GPS_RxID", "GPS_Timestamp_ms",
        "PosX_m", "PosY_m", "PosZ_m",
        "VelX_ms", "VelY_ms", "VelZ_ms",
        "TOW_s", "NumSats", "FixType", "CRC", "CRC_Valid"
    ]
    lines.append(','.join(header))
    
    for frame in report.frames:
        row = [
            str(frame.packet_number),
            f"{frame.timestamp:.6f}",
            frame.src_mac,
            frame.dst_mac,
            str(frame.vl_id),
            str(frame.sequence_number),
        ]
        
        if frame.gps_message:
            msg = frame.gps_message
            sat = msg.satellite_data
            row.extend([
                str(msg.message_id),
                str(msg.gps_receiver_id),
                str(msg.timestamp_ms),
                f"{sat.position_x:.2f}",
                f"{sat.position_y:.2f}",
                f"{sat.position_z:.2f}",
                f"{sat.velocity_x:.2f}",
                f"{sat.velocity_y:.2f}",
                f"{sat.velocity_z:.2f}",
                f"{sat.time_of_week:.3f}",
                str(sat.num_satellites),
                sat.fix_type_str(),
                f"0x{msg.checksum:08x}",
                str(msg.checksum_valid),
            ])
        else:
            row.extend([''] * 14)
            
        lines.append(','.join(row))
        
    return '\n'.join(lines)


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="Analyze AFDX PCAP files and generate reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s capture.pcap
  %(prog)s capture.pcap --output report.txt
  %(prog)s capture.pcap --csv data.csv
  %(prog)s capture.pcap --compare events.csv
  %(prog)s capture.pcap --compare events.csv --network NET_A
  %(prog)s capture.pcap --output report.txt --csv data.csv --compare events.csv
        """
    )
    
    parser.add_argument('pcap_file', help='PCAP file to analyze')
    parser.add_argument('--output', '-o', help='Output report file (text)')
    parser.add_argument('--csv', '-c', help='Output CSV file with frame data')
    parser.add_argument('--compare', help='CSV log file to compare payload data against')
    parser.add_argument('--network', choices=['NET_A', 'NET_B'],
                       help='Filter CSV entries by network (for comparison)')
    parser.add_argument('--event', choices=['AFDX_TX', 'AFDX_RX'],
                       default='AFDX_TX',
                       help='Filter CSV entries by event type (default: AFDX_TX)')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Suppress console output')
    
    args = parser.parse_args()
    
    try:
        # Analyze PCAP
        analyzer = PcapAnalyzer(args.pcap_file)
        report = analyzer.analyze()
        
        # Perform CSV comparison if requested
        if args.compare:
            if not os.path.exists(args.compare):
                print(f"Error: CSV file not found: {args.compare}", file=sys.stderr)
                return 1
                
            if not args.quiet:
                print(f"\nComparing with CSV: {args.compare}")
                if args.network:
                    print(f"  Network filter: {args.network}")
                print(f"  Event filter: {args.event}")
                
            # Parse CSV log
            csv_entries = CsvLogParser.parse_csv_file(
                args.compare,
                network_filter=args.network,
                event_filter=args.event
            )
            
            if not args.quiet:
                print(f"  Loaded {len(csv_entries)} CSV entries")
            
            # Compare
            comparator = PcapCsvComparator(report.frames, csv_entries)
            report.csv_comparison = comparator.compare()
        
        # Generate text report
        text_report = generate_text_report(report)
        
        if not args.quiet:
            print(text_report)
            
        if args.output:
            with open(args.output, 'w') as f:
                f.write(text_report)
            if not args.quiet:
                print(f"\nReport saved to: {args.output}")
                
        # Generate CSV if requested
        if args.csv:
            csv_report = generate_csv_report(report)
            with open(args.csv, 'w') as f:
                f.write(csv_report)
            if not args.quiet:
                print(f"CSV saved to: {args.csv}")
                
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error analyzing PCAP: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
