import tkinter as tk

class HybridTimer:
    def __init__(self, root):
        self.root = root
        self.root.title("Break Timer")
        self.root.geometry("350x480")
        self.root.resizable(False, False)
        
        # State variables
        self.is_work_phase = True
        self.running = False
        self.current_seconds = 0 
        self.target_seconds = 0
        self.timer_id = None

        self.create_widgets()
        self.reset_timer()

    def create_widgets(self):
        input_frame = tk.Frame(self.root)
        input_frame.pack(pady=10)

        # Work Inputs (Count-Up Target)
        tk.Label(input_frame, text="Work Duration:", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=4)
        self.work_min = tk.Entry(input_frame, width=5, justify='center')
        self.work_min.insert(0, "45")
        self.work_min.grid(row=1, column=0, padx=2)
        tk.Label(input_frame, text="m").grid(row=1, column=1, sticky="w")
        self.work_sec = tk.Entry(input_frame, width=5, justify='center')
        self.work_sec.insert(0, "00")
        self.work_sec.grid(row=1, column=2, padx=2)
        tk.Label(input_frame, text="s").grid(row=1, column=3, sticky="w")

        # Break Inputs (Count-Down Start)
        tk.Label(input_frame, text="Break Duration:", font=("Arial", 10, "bold")).grid(row=2, column=0, columnspan=4, pady=(10,0))
        self.break_min = tk.Entry(input_frame, width=5, justify='center')
        self.break_min.insert(0, "10")
        self.break_min.grid(row=3, column=0, padx=2)
        tk.Label(input_frame, text="m").grid(row=3, column=1, sticky="w")
        self.break_sec = tk.Entry(input_frame, width=5, justify='center')
        self.break_sec.insert(0, "00")
        self.break_sec.grid(row=3, column=2, padx=2)
        tk.Label(input_frame, text="s").grid(row=3, column=3, sticky="w")

        # Status & Timer Display
        self.status_label = tk.Label(self.root, text="Ready", font=("Arial", 14, "bold"))
        self.status_label.pack(pady=10)

        self.timer_label = tk.Label(self.root, text="00:00", font=("Courier", 45, "bold"))
        self.timer_label.pack()

        # Control Buttons
        self.btn_start_pause = tk.Button(self.root, text="Start", width=15, height=2, command=self.toggle_timer, bg="#2ecc71", fg="white", font=("Arial", 10, "bold"))
        self.btn_start_pause.pack(pady=5)

        self.btn_reset = tk.Button(self.root, text="Reset", width=15, command=self.reset_timer)
        self.btn_reset.pack(pady=5)

        self.btn_switch = tk.Button(self.root, text="Switch to Break", width=20, command=self.manual_switch, bg="#ecf0f1")
        self.btn_switch.pack(pady=20)

    def update_display(self):
        mins, secs = divmod(max(0, self.current_seconds), 60)
        self.timer_label.config(text=f"{mins:02d}:{secs:02d}")

    def toggle_timer(self):
        if not self.running:
            self.running = True
            self.btn_start_pause.config(text="Pause", bg="#f1c40f", fg="black")
            self.run_timer()
        else:
            self.stop_timer_logic()

    def stop_timer_logic(self):
        self.running = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        self.btn_start_pause.config(text="Start", bg="#2ecc71", fg="white")

    def run_timer(self):
        if not self.running:
            return
        
        self.update_display()

        if self.is_work_phase:
            # COUNT-UP LOGIC
            if self.current_seconds < self.target_seconds:
                self.current_seconds += 1
                self.timer_id = self.root.after(1000, self.run_timer)
            else:
                self.finish_phase()
        else:
            # COUNT-DOWN LOGIC
            if self.current_seconds > 0:
                self.current_seconds -= 1
                self.timer_id = self.root.after(1000, self.run_timer)
            else:
                self.finish_phase()

    def finish_phase(self):
        self.stop_timer_logic()
        self.show_completion_popup()

    def show_completion_popup(self):
        # Play the system default notification sound
        self.root.bell()
        popup = tk.Toplevel(self.root)
        popup.title("Time's Up!")
        popup.geometry("250x150")
        popup.attributes("-topmost", True)
        
        if self.is_work_phase:
            tk.Label(popup, text="Work period over! \nTime to have a break", font=("Arial", 12)).pack(pady=10)

            tk.Button(popup, text="Start a break", width=15, 
                    command=lambda: [popup.destroy(), self.manual_switch()]).pack(pady=2)
        else:
            tk.Label(popup, text="Break period over! \nTime to work", font=("Arial", 12)).pack(pady=10)

            tk.Button(popup, text="Start working", width=15, 
                    command=lambda: [popup.destroy(), self.manual_switch()]).pack(pady=2)

        tk.Button(popup, text="Extend +5 Mins", width=15, 
                  command=lambda: [popup.destroy(), self.extend_phase(5)]).pack(pady=2)

    def extend_phase(self, minutes):
        added_secs = minutes * 60
        if self.is_work_phase:
            # For count-up, extension means increasing the target
            self.target_seconds += added_secs
        else:
            # For count-down, extension means adding time to current
            self.current_seconds += added_secs
        self.update_display()
        self.toggle_timer()

    def reset_timer(self):
        self.stop_timer_logic()
        try:
            w_m, w_s = int(self.work_min.get() or 0), int(self.work_sec.get() or 0)
            b_m, b_s = int(self.break_min.get() or 0), int(self.break_sec.get() or 0)
            
            if self.is_work_phase:
                self.current_seconds = 0  # Start at zero for count-up
                self.target_seconds = (w_m * 60) + w_s
                self.status_label.config(text="WORKING", fg="#e74c3c")
                self.btn_switch.config(text="Switch to Break")
            else:
                self.current_seconds = (b_m * 60) + b_s # Start at max for count-down
                self.status_label.config(text="BREAK TIME", fg="#27ae60")
                self.btn_switch.config(text="Switch to Work")
            
            self.update_display()
        except ValueError:
            pass

    def manual_switch(self):
        self.is_work_phase = not self.is_work_phase
        self.reset_timer()
        self.toggle_timer()

if __name__ == "__main__":
    root = tk.Tk()
    app = HybridTimer(root)
    root.mainloop()