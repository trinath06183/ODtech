import os
import sys
import time
import webbrowser

SERVER_URL = "https://collar-mammal-strike.ngrok-free.dev/"

def main():
    print("==================================================")
    print("      ODtech Solutions Desktop Application       ")
    print("==================================================")
    print(f"Connecting to live server: {SERVER_URL}")

    # Try opening PyWebView desktop application window
    try:
        import webview
        print("Launching native desktop window...")
        window = webview.create_window(
            title="ODtech Solutions ERP",
            url=SERVER_URL,
            width=1366,
            height=768,
            resizable=True,
            min_size=(900, 600)
        )
        webview.start()
    except Exception as e:
        print(f"PyWebView desktop window notice ({e}). Opening web browser...")
        webbrowser.open(SERVER_URL)
        print("ODtech ERP desktop app is running connected to live server.")

if __name__ == '__main__':
    main()
