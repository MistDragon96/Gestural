import socket
import json
import threading
import subprocess
import os
import time
import logging
import select

dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(dir)                                   # Set current working directory to where the server.py is located

HOST = '127.0.0.1'  # Localhost
PORT = 65432        # Port to listen on
FORWARD_PORT = 65433        # New port for functionality.py to listen on

gesture_data_lock = threading.Lock()
shutdown_event = threading.Event()

with open("state.txt", "w") as file:             # to tell if the functionality program is running or not
    file.write("")

functionality_process_is_running = False

forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

logging.basicConfig(  # Configure logging
    filename=os.path.join(dir, "Gesture.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def start_server():
    global gesture_data

    # Start the client process
    client_process = subprocess.Popen(['python', 'gesture_to_list_vectors.py'])

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((HOST, PORT))
            server_socket.listen()
            print(f"Server listening on {HOST}:{PORT}")

            conn, addr = server_socket.accept()
            with conn:
                print(f"Connected by {addr}")

                # Buffer to store partial data
                buffer = ""

                while not shutdown_event.is_set():  # Check for shutdown signal
                    data = conn.recv(1024)  # Receive up to 1024 bytes
                    if not data:
                        break
                    # Append new data to buffer
                    buffer += data.decode('utf-8')

                    # Process complete messages (split by '\n')
                    while '\n' in buffer:
                        # Split on the first occurrence of the delimiter
                        message, buffer = buffer.split('\n', 1)
                        try:
                            # Parse JSON message
                            gesture_data = json.loads(message)

                            with gesture_data_lock:
                                gesture_data.update(gesture_data)
                                

                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON received. Error: {e}")
                            logging.error(f"Server Error: Invalid JSON received. Error: {e}")
                            print("Raw message:", message)

    except Exception as e:
        print(f"Server error: {e}")
        logging.error(f"Server Error: Server error: {e}")

    finally:
        # Terminate the client process when the server shuts down
        print("Server and client processes terminated.")
        # Signal the main thread to exit
        shutdown_event.set()
        with open(dir+"\\state.txt", "w") as file:             # to tell if the functionality program is running or not
            file.write("")

def forward_data_to_functionality():
    try:
        with gesture_data_lock:
            # Convert the Python dictionary to a JSON string
            json_data = json.dumps(gesture_data)
        # Send the JSON string to the server
        forward_socket.sendall((json_data + "\n").encode('utf-8'))
    except Exception as e:
        print(f"Error forwarding data: {e}")
        logging.error(f"Server Error: Error forwarding data: {e}")

if __name__ == "__main__":
    gesture_data = {'hand_result':[], "landmarks": []}
    gesture_data_copy = gesture_data.copy()

    # Start the server thread
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True  # Allow the thread to terminate when the main program exits
    server_thread.start()

    try:
        while not shutdown_event.is_set():  # Main loop checks for shutdown signal
            try:
                if gesture_data != gesture_data_copy:
                    with gesture_data_lock:
                        gesture_data_copy = gesture_data.copy()

                    if not functionality_process_is_running:
                    
                        try:
                            hand_result = gesture_data['hand_result']
                            if hand_result[1:] == [True, True, True, False, False]:
                                print("Signal Detected")
                                with gesture_data_lock:
                                    gesture_data['hand_result'] = [0, False, False, False, False, False]

                                functionality_process = subprocess.Popen(['python', 'functionality.py'])

                                with open(os.path.join(dir, "state.txt"), "w") as file:    # to tell if the functionality program is running or not
                                    file.write("True")

                                functionality_process_is_running = functionality_process.poll() is None

                                try:
                                    time.sleep(2)
                                    forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                    forward_socket.connect((HOST, FORWARD_PORT))
                                except Exception as e:
                                    print(f"Error connecting with functionality: {e}")
                                    logging.error(f"Server Error: Error connecting with functionality: {e}")

                        except KeyError:
                            print("No 'hand_result' key in gesture data")
                            logging.error("Server Error: No 'hand_result' key in gesture data")

                        except Exception as e:
                            print(f"An error occured: {e}")
                            logging.error(f"Server Error: An error occured: {e}")

                    else:
                        functionality_process_is_running = functionality_process.poll() is None
                        if functionality_process_is_running:
                            try:
                                # Forward data to functionality.py
                                forward_data_to_functionality()
                                
                            except Exception as e:
                                print(f"Error forwarding data: {e}")
                                logging.error(f"Server Error: Error forwarding data: {e}")
                        else:
                            forward_socket.close()
                            functionality_process.terminate()
                            
                            with gesture_data_lock:
                                gesture_data["hand_result"] = [0, False, False, False, False, False]
                            time.sleep(5)

            except Exception as e:
                print(f"An error occured. {e}")
                logging.error(f"Server Error: An error occured. {e}")
                shutdown_event.set()

    finally:
        server_thread.join()  # Wait for the server thread to finish
        forward_socket.close()
        functionality_process_is_running = functionality_process.poll() is None
        if functionality_process_is_running:
            functionality_process.terminate()
        with open(os.path.join(dir, "state.txt"), "w") as file:             # to tell if the functionality program is running or not
            file.write("")
        print("Main program exited.")
