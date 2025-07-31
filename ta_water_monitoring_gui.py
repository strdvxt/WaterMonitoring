from tkinter import *
import tkinter as tk
from tkinter.ttk import *
import socket
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
from datetime import datetime
import numpy as np
import struct
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import Style

# Configuration
ESP32_IP = "192.168.1.100"  # Update with your ESP32's IP
ESP32_PORT = 80
SSID = "titanium"
PASSWORD = "titanium"

# Define headers
HEADERS = [
    'waktu', 'save_pH', 'value_pH', 'interval_pH', 
    'save_temp', 'value_temp', 'interval_temp', 
    'save_DO', 'value_DO', 'interval_DO', 
    'save_turb', 'value_turb', 'interval_turb', 
    'current', 'voltage'
]

class WaterQualityApp:
    
    def __init__(self, root):
        self.root = root
        self.root.title("Water Quality Test")
        self.root.geometry("900x600")
        
        # Initialize data storage
        self.test_completed = False
        self.raw_data = []
        self.parsed_data = []
        self.last_data_hash = None
        self.response_text = ""
        
        # Create container frame
        self.container = tk.Frame(root)
        self.container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create pages
        self.pages = {}
        for PageClass in (InputPage, ResultsPage):
            page_name = PageClass.__name__
            frame = PageClass(parent=self.container, controller=self)
            self.pages[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")
        
        self.show_page("InputPage")
    
    def show_page(self, page_name):
        frame = self.pages[page_name]
        frame.tkraise()
        
        # Special handling for ResultsPage
        if page_name == "ResultsPage":
            frame.update_display()
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"
    
    def send_to_esp32(self, depth, duration, save):
        try:
            # Create TCP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)  # Increased timeout for data transfer
            sock.connect((ESP32_IP, ESP32_PORT))
            
            # Create byte array with signature and data
            data = bytearray()
            
            # Add signature "ABC" (3 bytes)
            data.extend(b'ABC')
            
            # Add depth as integer (4 bytes)
            data.extend(struct.pack('i', int(depth)))
            
            # Add duration as integer (4 bytes)
            data.extend(struct.pack('i', int(duration)))
            
            # Add save status (1 byte)
            data.extend(struct.pack('B', 1 if save else 0))
            
            # Send data
            sock.sendall(data)
            
            # Create file-like object for reading lines
            sock_file = sock.makefile('r')
            
            # Read response line by line
            response_lines = []
            finished = False
            
            while not finished:
                line = sock_file.readline().strip()
                if not line:
                    break
                
                # Check if this is the last line
                if ';' in line:
                    tokens = line.split(';')
                    # Last token is the sd_card_finished flag
                    if tokens and tokens[-1] == '1':
                        finished = True
                
                response_lines.append(line)
            
            sock_file.close()
            return response_lines
            
        except socket.timeout:
            return "Error: ESP32 response timeout"
        except ConnectionRefusedError:
            return "Error: Connection refused (ESP32 offline?)"
        except OSError as e:
            return f"Network Error: {str(e)}"
        except struct.error as e:
            return f"Data packing error: {str(e)}"
        finally:
            try:
                sock.close()
            except:
                pass
    
    def parse_response_data(self, response_lines):
        """Parse the ESP32 response into structured data"""
        self.raw_data = []
        self.parsed_data = []
        
        if isinstance(response_lines, str):
            return
            
        for line in response_lines:
            if not line:
                continue
                
            tokens = line.split(';')
            if len(tokens) < 16:
                continue
                
            try:
                # Safely convert numeric fields
                reading = {
                    'waktu': tokens[0],
                    'save_pH': int(round(float(tokens[1]))),
                    'value_pH': float(tokens[2]),
                    'interval_pH': int(round(float(tokens[3]))),
                    'save_temp': int(round(float(tokens[4]))),
                    'value_temp': float(tokens[5]),
                    'interval_temp': int(round(float(tokens[6]))),
                    'save_DO': int(round(float(tokens[7]))),
                    'value_DO': float(tokens[8]),
                    'interval_DO': int(round(float(tokens[9]))),
                    'save_turb': int(round(float(tokens[10]))),
                    'value_turb': float(tokens[11]),
                    'interval_turb': int(round(float(tokens[12]))),
                    'current': float(tokens[13]),
                    'voltage': float(tokens[14])
                }
                self.parsed_data.append(reading)
                self.raw_data.append(line)
            except (ValueError, TypeError, IndexError) as e:
                print(f"Error parsing line: {line}\nError: {str(e)}")
    
    def start_test(self, depth, duration, save):
        # Validate inputs
        try:
            depth_val = int(depth)
            duration_val = int(duration)
            
        except:
            self.pages["InputPage"].update_response("Error: Masukkan angka yang valid")
            return
        
        # Show sending message
        self.pages["InputPage"].update_response("Mengirim ke ESP32...")
        self.test_completed = False
        
        # Send in separate thread
        def communication_thread():
            response = self.send_to_esp32(depth, duration, save)
            self.response_text = response
            
            if isinstance(response, str) and response.startswith("Error:"):
                # Handle network errors
                self.test_completed = False
                self.response_text = response
                # Update response in ResultsPage
                self.root.after(0, lambda: self.pages["ResultsPage"].update_response(response))
            else:
                try:
                    # Parse string data
                    self.parse_response_data(response)
                    self.test_completed = True
                    # Update response with success message
                    success_msg = f"Berhasil menerima {len(self.parsed_data)} data"
                    self.root.after(0, lambda: self.pages["ResultsPage"].update_response(success_msg))
                except Exception as e:
                    self.test_completed = False
                    error_msg = f"Data parsing error: {str(e)}"
                    self.response_text = error_msg
                    self.root.after(0, lambda: self.pages["ResultsPage"].update_response(error_msg))
            
            # Switch to results page
            self.root.after(0, lambda: self.show_page("ResultsPage"))
        
        threading.Thread(target=communication_thread, daemon=True).start()
    
    def get_last_valid_reading(self, save_key, value_key, interval_key):
        """Find the last valid reading for a specific parameter"""
        for data in reversed(self.parsed_data):
            if data[save_key] == 1:  # Only consider valid readings
                return data[value_key], data[interval_key]
        return None, None
    
    def save_data(self):
        """Save test data to CSV file"""
        if not self.raw_data:
            self.pages["ResultsPage"].update_response("Tidak ada data untuk disimpan")
            return
        
        filename = f"water_quality_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            with open(filename, 'w', newline='') as csvfile:
                # Write header
                writer = csv.writer(csvfile, delimiter=';')
                writer.writerow(HEADERS)
                
                # Write data
                for data in self.raw_data:
                    # Only write the first 15 tokens (ignore sd_card_finished)
                    writer.writerow(data.split(';')[:15])
            
            self.pages["ResultsPage"].update_response(f"Data disimpan sebagai {filename}")
        except Exception as e:
            self.pages["ResultsPage"].update_response(f"Gagal menyimpan: {str(e)}")
    
    def show_graph(self):
        """Display water quality graphs with value and interval plots"""
        if not self.parsed_data:
            self.pages["ResultsPage"].update_response("Tidak ada data untuk ditampilkan")
            return
        
        # Create a new window for graphs
        graph_window = tk.Toplevel(self.root)
        graph_window.title("Grafik Kualitas Air")
        graph_window.geometry("1000x800")
        
        # Create figure for plots - 4 rows, 2 columns
        fig, axs = plt.subplots(4, 2, figsize=(12, 16))
        fig.suptitle("Parameter Kualitas Air dengan Interval Sampling", fontsize=12)
        
        # Convert waktu to seconds since first reading
        time_seconds = []
        base_time = None
        for data in self.parsed_data:
            t = data['waktu']
            parts = t.split(':')
            if len(parts) == 4:
                try:
                    # Convert H:M:S:ms to total seconds
                    total_seconds = (int(parts[0]) * 3600 + 
                                    int(parts[1]) * 60 + 
                                    int(parts[2]) + 
                                    int(parts[3])/1000.0)
                    if base_time is None:
                        base_time = total_seconds
                    time_seconds.append(total_seconds - base_time)
                except:
                    time_seconds.append(0.0)
            else:
                time_seconds.append(0.0)
        
        # Initialize lists for valid data
        valid_ph = {'time': [], 'value': []}
        valid_temp = {'time': [], 'value': []}
        valid_do = {'time': [], 'value': []}
        valid_turb = {'time': [], 'value': []}
        
        # Collect only valid readings based on save flags
        for i, data in enumerate(self.parsed_data):
            if data['save_pH'] == 1:
                valid_ph['time'].append(time_seconds[i])
                valid_ph['value'].append(data['value_pH'])
                
            if data['save_temp'] == 1:
                valid_temp['time'].append(time_seconds[i])
                valid_temp['value'].append(data['value_temp'])
                
            if data['save_DO'] == 1:
                valid_do['time'].append(time_seconds[i])
                valid_do['value'].append(data['value_DO'])
                
            if data['save_turb'] == 1:
                valid_turb['time'].append(time_seconds[i])
                valid_turb['value'].append(data['value_turb'])
        
        # Plot pH values and intervals
        self.plot_parameter(axs[0, 0], axs[0, 1], 
                           valid_ph['value'],
                           [d['interval_pH']/1000 for d in self.parsed_data if d['save_pH'] == 1],
                           valid_ph['time'],
                           'pH', 'pH Value', 'pH Sampling Interval (s)')
        
        # Plot Temperature values and intervals
        self.plot_parameter(axs[1, 0], axs[1, 1], 
                           valid_temp['value'],
                           [d['interval_temp']/1000 for d in self.parsed_data if d['save_temp'] == 1],
                           valid_temp['time'],
                           'Temperature', 'Temperature (°C)', 'Temp Sampling Interval (s)')
        
        # Plot Dissolved Oxygen values and intervals
        self.plot_parameter(axs[2, 0], axs[2, 1], 
                           valid_do['value'],
                           [d['interval_DO']/1000 for d in self.parsed_data if d['save_DO'] == 1],
                           valid_do['time'],
                           'Dissolved Oxygen', 'DO (mg/L)', 'DO Sampling Interval (s)')
        
        # Plot Turbidity values and intervals
        self.plot_parameter(axs[3, 0], axs[3, 1], 
                           valid_turb['value'],
                           [d['interval_turb']/1000 for d in self.parsed_data if d['save_turb'] == 1],
                           valid_turb['time'],
                           'Turbidity', 'Turbidity (NTU)', 'Turb Sampling Interval (s)')
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.subplots_adjust(hspace=0.5)

        # Embed plot in Tkinter window
        canvas = FigureCanvasTkAgg(fig, master=graph_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add a close button
        close_btn = tk.Button(graph_window, text="Tutup", 
                             command=graph_window.destroy,
                             bg="#f44336", fg="white", padx=10, pady=5)
        close_btn.pack(pady=10)
    
    def plot_parameter(self, value_ax, interval_ax, values, intervals, timestamps, 
                      title, value_label, interval_label):
        """Plot parameter values and intervals in two subplots"""
        # Plot values
        value_ax.plot(timestamps, values, 'b-o')
        value_ax.set_title(title + ' Values')
        value_ax.set_ylabel(value_label)
        value_ax.grid(True)
        plt.subplots_adjust(hspace=0.5)
        
        # Plot intervals
        if intervals:  # Only plot if we have interval data
            interval_ax.plot(timestamps, intervals, 'r-o')
            interval_ax.set_title(title + ' Sampling Intervals')
            interval_ax.set_ylabel(interval_label)
            interval_ax.grid(True)
            
            # Add horizontal line for average interval
            if len(intervals) > 0:
                avg_interval = np.mean(intervals)
                interval_ax.axhline(y=avg_interval, color='g', linestyle='--', 
                                   label=f'Avg: {avg_interval:.2f} s')
                interval_ax.legend()

class InputPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="#ffffff")
        style=Style(theme='darkly')
        # Header
        header_frame = tk.Frame(self, bg="#009DFF")
        header_frame.pack(fill="x", pady=(0, 15))
        
        title = Label(header_frame, 
                     text="Selamat Datang Di Pengujian Kualitas Air", 
                     font=("Arial Bold", 16), 
                     bg="#009DFF", fg="white")
        title.pack(pady=10)
        
        # Main content
        main_frame = tk.Frame(self, padx=20, pady=10, bg="#ffffff")
        main_frame.pack(fill="both", expand=True)
        
        # Input fields
        depth_label = Label(main_frame, text="Kedalaman (m):", font="Arial", bg="#ffffff")
        duration_label = Label(main_frame, text="Durasi Pengujian (menit):", font="Arial", bg="#ffffff")
        
        self.depth_entry = Entry(main_frame, width=20)
        self.duration_entry = Entry(main_frame, width=20)
        
        # Buttons
        send_btn = Button(main_frame, text="Kirim", 
                          command=self.send_test, width=15, bg="#009DFF", fg="#ffffff")
        ambil_btn = Button(main_frame, text="Ambil Data", 
                          command=self.start_test, width=15, bg="#4CAF50", fg="#ffffff")
        
        # Response display
        self.response_var = StringVar()
        response_label = Label(main_frame, textvariable=self.response_var, 
                              fg="blue", wraplength=400, justify="left", bg="#ffffff")
        
        # IP display
        computer_ip = self.controller.get_local_ip()
        ip_info = f"Computer IP: {computer_ip}\nESP32 IP: {ESP32_IP}\nSSID: {SSID}"
        ip_label = Label(main_frame, text=ip_info, fg="green", justify="left", bg="#ffffff")
        
        # Layout
        depth_label.grid(row=0, column=0, sticky="w", pady=5)
        self.depth_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        duration_label.grid(row=1, column=0, sticky="w", pady=5)
        self.duration_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        send_btn.grid(row=2, column=0, pady=10, padx=5)
        ambil_btn.grid(row=2, column=1, pady=10, padx=5)
        response_label.grid(row=3, column=0, columnspan=2, pady=5, sticky="w")
        ip_label.grid(row=4, column=0, columnspan=2, pady=5, sticky="w")
        
        # Configure grid columns
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
    
    def send_test(self):
        depth = self.depth_entry.get()
        duration = self.duration_entry.get()
        self.controller.start_test(depth, duration, save=False)
    
    def start_test(self):
        depth = self.depth_entry.get()
        duration = self.duration_entry.get()
        self.controller.start_test(depth, duration, save=True)
    
    def update_response(self, message):
        self.response_var.set(message)

class ResultsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="#ffffff")
        
        # Header
        header_frame = tk.Frame(self, bg="#009DFF")
        header_frame.pack(fill="x", pady=(0, 15))
        
        title = Label(header_frame, 
                     text="Hasil Pengujian", 
                     font=("Arial Bold", 16), 
                     bg="#009DFF", fg="white")
        title.pack(pady=10)
        
        # Status and response
        status_frame = tk.Frame(self, bg="#ffffff", pady=10)
        status_frame.pack(fill="x", padx=7)
        
        self.status_var = StringVar(value="Status: Pengujian sedang berlangsung...")
        status_label = Label(status_frame, textvariable=self.status_var, 
                            font=("Arial", 12), bg="#ffffff", fg="#ff9800")
        status_label.pack(anchor="w")
        
        self.response_var = StringVar()
        response_label = Label(status_frame, textvariable=self.response_var, 
                              fg="blue", wraplength=300, justify="left", bg="#ffffff")
        response_label.pack(anchor="w", pady=5)
        
        # Main content
        content_frame = tk.Frame(self, bg="#ffffff")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left panel - Buttons
        button_frame = tk.Frame(content_frame, bg="#e0e0e0", padx=10, pady=10)
        button_frame.pack(side="left", fill="y", padx=(0, 10))
        
        self.save_btn = Button(
            button_frame,
            text="Simpan Data",
            command=self.controller.save_data,
            width=15,
            bg="#4CAF50",
            fg="white",
            state="disabled"
        )
        self.save_btn.pack(pady=10)
        
        self.graph_btn = Button(
            button_frame,
            text="Tampilkan Grafik",
            command=self.controller.show_graph,
            width=15,
            bg="#2196F3",
            fg="white",
            state="disabled"
        )
        self.graph_btn.pack(pady=10)
        
        # Right panel - Results
        results_frame = tk.Frame(content_frame, bg="#ffffff", padx=10, pady=10)
        results_frame.pack(side="right", fill="both", expand=True)
        
        # Section title
        tk.Label(
            results_frame,
            text="Parameter Kualitas Air",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            anchor="w"
        ).pack(fill="x", pady=(0, 10))
        
        # Results grid
        grid_frame = tk.Frame(results_frame, bg="#ffffff")
        grid_frame.pack(fill="both", expand=True)
        
        # Column headers
        tk.Label(
            grid_frame,
            text="Parameter",
            font=("Arial", 12, "bold"),
            bg="#e0e0e0",
            width=20,
            padx=10,
            pady=5
        ).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        
        tk.Label(
            grid_frame,
            text="Nilai",
            font=("Arial", 12, "bold"),
            bg="#e0e0e0",
            width=20,
            padx=10,
            pady=5
        ).grid(row=0, column=1, sticky="ew", padx=1, pady=1)
        
        tk.Label(
            grid_frame,
            text="Interval Sampling",
            font=("Arial", 12, "bold"),
            bg="#e0e0e0",
            width=20,
            padx=10,
            pady=5
        ).grid(row=0, column=2, sticky="ew", padx=1, pady=1)
        
        # Parameter rows
        self.param_labels = {}
        
        parameters = [
            ("pH", ""),
            ("Suhu", "°C"),
            ("Oksigen Terlarut", "mg/L"),
            ("Turbidity", "NTU")
        ]
        
        for i, (param, unit) in enumerate(parameters, start=1):
            # Parameter name
            tk.Label(
                grid_frame,
                text=param,
                font=("Arial", 11),
                bg="#f5f5f5",
                width=20,
                padx=10,
                pady=5,
                anchor="w"
            ).grid(row=i, column=0, sticky="ew", padx=1, pady=1)
            
            # Value
            value_label = tk.Label(
                grid_frame,
                text="-",
                font=("Arial", 11),
                bg="#ffffff",
                width=20,
                padx=10,
                pady=5,
                anchor="center"
            )
            value_label.grid(row=i, column=1, sticky="ew", padx=1, pady=1)
            self.param_labels[f"{param.lower().replace(' ', '_')}_value"] = value_label
            
            # Interval
            interval_label = tk.Label(
                grid_frame,
                text="-",
                font=("Arial", 11),
                bg="#ffffff",
                width=20,
                padx=10,
                pady=5,
                anchor="center"
            )
            interval_label.grid(row=i, column=2, sticky="ew", padx=1, pady=1)
            self.param_labels[f"{param.lower().replace(' ', '_')}_interval"] = interval_label
        
        # Data display
        data_frame = tk.Frame(results_frame, bg="#ffffff", pady=10)
        data_frame.pack(fill="both", expand=True)
        
        tk.Label(
            data_frame,
            text="Data Terakhir:",
            font=("Arial", 12, "bold"),
            bg="#ffffff",
            anchor="w"
        ).pack(fill="x", pady=(10, 5))
        
        self.data_var = StringVar()
        data_label = tk.Label(
            data_frame,
            textvariable=self.data_var,
            font=("Courier", 10),
            bg="#f0f0f0",
            padx=10,
            pady=5,
            anchor="w",
            justify="left",
            wraplength=300
        )
        data_label.pack(fill="x")
        
        # Back button
        back_frame = tk.Frame(self, bg="#ffffff", pady=20)
        back_frame.pack(fill="x")
        
        back_btn = Button(
            back_frame,
            text="Kembali ke Input",
            command=lambda: self.controller.show_page("InputPage"),
            bg="#9E9E9E",
            fg="white",
            padx=15,
            pady=5
        )
        back_btn.pack()
    
    def update_display(self):
        """Update the display with test results"""
        if self.controller.test_completed and self.controller.parsed_data:
            # Update status
            self.status_var.set("Status: Pengujian Selesai")
            
            # Enable buttons
            self.save_btn.config(state="normal")
            self.graph_btn.config(state="normal")
            
            # Get last valid readings
            # pH
            ph_value, ph_interval = self.controller.get_last_valid_reading('save_pH', 'value_pH', 'interval_pH')
            if ph_value is not None:
                self.param_labels['ph_value'].config(text=f"{ph_value:.2f}")
                self.param_labels['ph_interval'].config(text=f"{ph_interval/1000:.1f} detik")
            else:
                self.param_labels['ph_value'].config(text="Tidak ada data")
                self.param_labels['ph_interval'].config(text="Tidak ada data")
            
            # Temperature
            temp_value, temp_interval = self.controller.get_last_valid_reading('save_temp', 'value_temp', 'interval_temp')
            if temp_value is not None:
                self.param_labels['suhu_value'].config(text=f"{temp_value:.2f} °C")
                self.param_labels['suhu_interval'].config(text=f"{temp_interval/1000:.1f} detik")
            else:
                self.param_labels['suhu_value'].config(text="Tidak ada data")
                self.param_labels['suhu_interval'].config(text="Tidak ada data")
            
            # Dissolved Oxygen
            do_value, do_interval = self.controller.get_last_valid_reading('save_DO', 'value_DO', 'interval_DO')
            if do_value is not None:
                self.param_labels['oksigen_terlarut_value'].config(text=f"{do_value:.2f} mg/L")
                self.param_labels['oksigen_terlarut_interval'].config(text=f"{do_interval/1000:.1f} detik")
            else:
                self.param_labels['oksigen_terlarut_value'].config(text="Tidak ada data")
                self.param_labels['oksigen_terlarut_interval'].config(text="Tidak ada data")
            
            # Turbidity
            turb_value, turb_interval = self.controller.get_last_valid_reading('save_turb', 'value_turb', 'interval_turb')
            if turb_value is not None:
                self.param_labels['turbidity_value'].config(text=f"{turb_value:.2f} NTU")
                self.param_labels['turbidity_interval'].config(text=f"{turb_interval/1000:.1f} detik")
            else:
                self.param_labels['turbidity_value'].config(text="Tidak ada data")
                self.param_labels['turbidity_interval'].config(text="Tidak ada data")
            
            # Show last data string
            if self.controller.raw_data:
                self.data_var.set(self.controller.raw_data[-1])
        else:
            # Show in-progress status
            self.status_var.set("Status: Pengujian sedang berlangsung...")
            
            # Disable buttons until test completes
            self.save_btn.config(state="disabled")
            self.graph_btn.config(state="disabled")
            
            # Schedule another update
            self.after(1000, self.update_display)
    
    def update_response(self, message):
        self.response_var.set(message)

if __name__ == "__main__":
    root = tk.Tk()
    app = WaterQualityApp(root)
    root.mainloop()
