import eel
import logging
import json
import os
import subprocess
from datetime import datetime
import psutil
import time
import re
from collections import deque
import screeninfo 
import sys
import shutil
from pathlib import Path

# Tambahkan variable untuk menyimpan log
log_buffer = deque(maxlen=100)

class LogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = [
                record.asctime,
                record.levelname,
                record.getMessage()
            ]
            log_buffer.append(log_entry)
        except Exception:
            pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(),
        LogHandler()  # Tambahkan custom handler
    ]
)

class ProxyManager:
    def __init__(self):
        self.assigned_proxies = {}
        self.proxy_file = 'proxy.json'
        self.assignments_file = 'assignments.json'
        self.ensure_files_exist()
        self.load_assignments()

    def ensure_files_exist(self):
        if not os.path.exists(self.proxy_file):
            with open(self.proxy_file, 'w') as f:
                json.dump([], f, indent=4)
        if not os.path.exists(self.assignments_file):
            with open(self.assignments_file, 'w') as f:
                json.dump({}, f, indent=4)

    def load_proxies(self):
        try:
            with open(self.proxy_file, 'r') as f:
                data = json.load(f)
                # Pastikan mengembalikan list
                return data if isinstance(data, list) else []
        except Exception as e:
            logging.error(f"Error loading proxies: {str(e)}")
            return []

    def save_proxies(self, proxies):
        try:
            # Pastikan menyimpan dalam format list
            with open(self.proxy_file, 'w') as f:
                json.dump(list(set(proxies)), f, indent=4)
            return True
        except Exception as e:
            logging.error(f"Error saving proxies: {str(e)}")
            return False

    def load_assignments(self):
        try:
            with open(self.assignments_file, 'r') as f:
                self.assigned_proxies = json.load(f)
        except Exception as e:
            logging.error(f"Error loading assignments: {str(e)}")
            self.assigned_proxies = {}

    def save_assignments(self):
        try:
            with open(self.assignments_file, 'w') as f:
                json.dump(self.assigned_proxies, f, indent=4)
            return True
        except Exception as e:
            logging.error(f"Error saving assignments: {str(e)}")
            return False

    def assign_proxy(self, proxy, device_id):
        self.assigned_proxies[proxy] = device_id
        self.save_assignments()

    def unassign_proxy(self, proxy):
        if proxy in self.assigned_proxies:
            del self.assigned_proxies[proxy]
            self.save_assignments()

    def get_proxy_for_device(self, device_id):
        for proxy, assigned_device in self.assigned_proxies.items():
            if assigned_device == device_id:
                return proxy
        return None

proxy_manager = ProxyManager()

def get_adb_path():
    # Get the base path (either in dev or in PyInstaller bundle)
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Path ke folder platform-tools yang berisi adb
    platform_tools = os.path.join(base_path, 'platform-tools')
    
    # Path ke executable adb
    if sys.platform == 'win32':
        adb_path = os.path.join(platform_tools, 'adb.exe')
    else:
        adb_path = os.path.join(platform_tools, 'adb')
    
    return adb_path

def check_adb_installation():
    adb_path = get_adb_path()
    if not os.path.exists(adb_path):
        logging.error(f"ADB not found at {adb_path}")
        return False
    return True

def run_adb_command(command, device_id=None):
    try:
        adb_path = get_adb_path()
        if not adb_path:
            return None
            
        if device_id:
            full_command = [adb_path, '-s', device_id] + command
        else:
            full_command = [adb_path] + command
            
        # Sembunyikan console window dengan lebih baik
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # Tambahkan DETACHED_PROCESS
        )
        return result
    except Exception as e:
        logging.error(f"Error running ADB command {command}: {str(e)}")
        return None

@eel.expose
def get_connected_devices():
    try:
        result = run_adb_command(['devices', '-l'])
        if not result or result.returncode != 0:
            return []
        
        devices = []
        for line in result.stdout.split('\n')[1:]:
            if line.strip() and 'device' in line:
                device_id = line.split()[0]
                state = line.split()[1]
                
                model = "Offline Device"
                if state == 'device':
                    model_result = run_adb_command(['shell', 'getprop', 'ro.product.model'], device_id)
                    if model_result and model_result.returncode == 0:
                        model = model_result.stdout.strip()
                
                devices.append({
                    'id': device_id,
                    'model': model,
                    'status': state
                })
        
        logging.info(f"Found {len(devices)} connected devices")
        return devices
    except Exception as e:
        logging.error(f"Error getting devices: {str(e)}")
        return []

@eel.expose
def load_proxies():
    return proxy_manager.load_proxies()

@eel.expose
def get_assignments():
    try:
        # Return current assignments with device info
        assignments = {}
        for proxy, device_id in proxy_manager.assigned_proxies.items():
            device = next((d for d in get_connected_devices() if d['id'] == device_id), None)
            assignments[proxy] = {
                'device_id': device_id,
                'device_model': device['model'] if device else 'Unknown Device'
            }
        return assignments
    except Exception as e:
        logging.error(f"Error getting assignments: {str(e)}")
        return {}

@eel.expose
def add_proxies(new_proxies):
    try:
        # Pastikan new_proxies adalah list
        if isinstance(new_proxies, str):
            new_proxies = [new_proxies]
        elif not isinstance(new_proxies, list):
            new_proxies = list(new_proxies)

        # Load existing proxies
        current_proxies = proxy_manager.load_proxies()
        if not isinstance(current_proxies, list):
            current_proxies = []
            
        logging.debug(f"Current proxies: {current_proxies}")
        logging.debug(f"New proxies: {new_proxies}")

        # Combine and remove duplicates
        all_proxies = current_proxies + new_proxies
        unique_proxies = list(set(all_proxies))
        
        # Validate format
        valid_proxies = []
        for proxy in unique_proxies:
            try:
                ip, port = proxy.split(':')
                if port.isdigit():
                    valid_proxies.append(proxy)
            except ValueError:
                logging.warning(f"Invalid proxy format: {proxy}")
                continue

        # Save valid proxies
        success = proxy_manager.save_proxies(valid_proxies)
        if success:
            logging.info(f"Successfully added proxies. Total proxies: {len(valid_proxies)}")
            return True
        return False
        
    except Exception as e:
        logging.error(f"Error adding proxies: {str(e)}")
        return False

@eel.expose
def delete_proxies(proxies_to_delete):
    try:
        current_proxies = proxy_manager.load_proxies()
        updated_proxies = [p for p in current_proxies if p not in proxies_to_delete]
        
        # Unassign deleted proxies
        for proxy in proxies_to_delete:
            proxy_manager.unassign_proxy(proxy)
            
        success = proxy_manager.save_proxies(updated_proxies)
        return success
    except Exception as e:
        logging.error(f"Error deleting proxies: {str(e)}")
        return False

@eel.expose
def delete_all_proxies():
    try:
        # Unassign all proxies
        proxy_manager.assigned_proxies.clear()
        proxy_manager.save_assignments()
        
        success = proxy_manager.save_proxies([])
        return success
    except Exception as e:
        logging.error(f"Error deleting all proxies: {str(e)}")
        return False

@eel.expose
def assign_single_proxy(device_id, proxy):
    try:
        # Unassign existing proxy for this device
        old_proxy = proxy_manager.get_proxy_for_device(device_id)
        if old_proxy:
            proxy_manager.unassign_proxy(old_proxy)
            run_adb_command(['shell', 'settings', 'put', 'global', 'http_proxy', ':0'], device_id)
        
        # Check if proxy is already assigned
        if proxy in proxy_manager.assigned_proxies:
            return False, "Proxy sudah digunakan oleh device lain"
        
        # Set new proxy
        try:
            ip, port = proxy.split(':')
            result = run_adb_command(['shell', 'settings', 'put', 'global', 'http_proxy', f'{ip}:{port}'], device_id)
            
            if result and result.returncode == 0:
                proxy_manager.assign_proxy(proxy, device_id)
                return True, "Berhasil mengatur proxy"
            return False, "Gagal mengatur proxy di device"
        except ValueError:
            return False, "Format proxy tidak valid (gunakan format ip:port)"
            
    except Exception as e:
        logging.error(f"Error assigning proxy: {str(e)}")
        return False, f"Error: {str(e)}"

@eel.expose
def unassign_proxy(proxy):
    try:
        device_id = proxy_manager.assigned_proxies.get(proxy)
        if device_id:
            result = run_adb_command(['shell', 'settings', 'delete', 'global', 'http_proxy'], device_id)
            if result and result.returncode == 0:
                proxy_manager.unassign_proxy(proxy)
                return True
            return False
        return True
    except Exception as e:
        logging.error(f"Error unassigning proxy: {str(e)}")
        return False

@eel.expose
def unassign_all_proxies():
    try:
        for proxy, device_id in proxy_manager.assigned_proxies.items():
            run_adb_command(['shell', 'settings', 'put', 'global', 'http_proxy', ':0'], device_id)
        
        proxy_manager.assigned_proxies.clear()
        proxy_manager.save_assignments()
        return True
    except Exception as e:
        logging.error(f"Error unassigning all proxies: {str(e)}")
        return False

@eel.expose
def bulk_assign_proxies():
    try:
        # Get available devices and proxies
        available_devices = [d for d in get_connected_devices() if d['status'] == 'device']
        all_proxies = proxy_manager.load_proxies()
        
        # Get unassigned proxies
        assigned_proxies = set(proxy_manager.assigned_proxies.keys())
        available_proxies = [p for p in all_proxies if p not in assigned_proxies]
        
        logging.info(f"Available devices: {len(available_devices)}")
        logging.info(f"Available proxies: {len(available_proxies)}")
        
        if not available_devices:
            logging.warning("No available devices found")
            return False, "Tidak ada device yang tersedia"
            
        if not available_proxies:
            logging.warning("No available proxies found")
            return False, "Tidak ada proxy yang tersedia"
            
        # Assign proxies to devices
        assignments = []
        for device in available_devices:
            if not available_proxies:
                break
                
            proxy = available_proxies.pop(0)
            success, message = assign_single_proxy(device['id'], proxy)
            
            if success:
                assignments.append((device['id'], proxy))
                logging.info(f"Successfully assigned {proxy} to {device['id']}")
            else:
                logging.warning(f"Failed to assign proxy to device {device['id']}: {message}")
                
        if assignments:
            logging.info(f"Successfully assigned {len(assignments)} proxies")
            return True, f"Berhasil mengatur {len(assignments)} proxy"
        
        logging.warning("No successful assignments made")
        return False, "Gagal mengatur proxy"
            
    except Exception as e:
        logging.error(f"Error in bulk assign: {str(e)}")
        return False, f"Error: {str(e)}"

@eel.expose
def get_network_stats():
    try:
        # Get network stats
        net_io = psutil.net_io_counters()
        
        # Get current timestamp
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        stats = {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'timestamp': timestamp
        }
        
        return stats
    except Exception as e:
        logging.error(f"Error getting network stats: {str(e)}")
        return None

@eel.expose
def get_recent_logs():
    try:
        return list(log_buffer)
    except Exception as e:
        logging.error(f"Error getting logs: {str(e)}")
        return []

@eel.expose
def clear_logs():
    try:
        log_buffer.clear()
        return True
    except Exception as e:
        logging.error(f"Error clearing logs: {str(e)}")
        return False

@eel.expose
def delete_all_device_proxies():
    try:
        devices = get_connected_devices()
        success = True
        
        for device in devices:
            if device['status'] == 'device':
                # Use ":0" to disable proxy instead of delete command
                result = run_adb_command(['shell', 'settings', 'put', 'global', 'http_proxy', ':0'], device['id'])
                if not result or result.returncode != 0:
                    logging.error(f"Failed to delete proxy for device {device['id']}")
                    success = False
        
        # Clear all assignments since we've removed all proxies
        proxy_manager.assigned_proxies.clear()
        proxy_manager.save_assignments()
        
        logging.info("Successfully deleted proxies from all devices")
        return success
    except Exception as e:
        logging.error(f"Error deleting device proxies: {str(e)}")
        return False

def get_center_position(width, height):
    # Get primary monitor
    monitors = screeninfo.get_monitors()
    if not monitors:
        return 0, 0
    
    primary = monitors[0]
    x = (primary.width - width) // 2
    y = (primary.height - height) // 2
    return x, y

if __name__ == '__main__':
    try:
        # Set window size dan position
        window_width = 1280
        window_height = 800
        x, y = get_center_position(window_width, window_height)
        
        # Konfigurasi window
        eel.init('web')
        eel.start(
            'index.html',
            size=(window_width, window_height),
            position=(x, y),
            mode='chrome',
            port=0,
            cmdline_args=[
                '--start-maximized',
                '--disable-gpu',
                '--disable-dev-tools'
            ]
        )
    except Exception as e:
        logging.error(f"Error starting application: {str(e)}")
