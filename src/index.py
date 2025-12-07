#!/usr/bin/env python3
import tkinter as tk

def main():
    # Create the main window
    root = tk.Tk()
    root.title("Hello Raspberry Pi")
    root.geometry("300x150")  # width x height in pixels

    # Center content using a frame
    frame = tk.Frame(root)
    frame.pack(expand=True)

    # A simple label
    label = tk.Label(frame, text="Hello, Raspberry Pi!", font=("Arial", 16))
    label.pack(pady=10)

    # A button that changes the label text
    def on_button_click():
        label.config(text="Button clicked!")

    button = tk.Button(frame, text="Click me", command=on_button_click)
    button.pack(pady=5)

    # Start the Tkinter event loop
    root.mainloop()

if __name__ == "__main__":
    main()
