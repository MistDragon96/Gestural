import cv2
import mediapipe as mp
import json
import socket
import keyboard
import time
from multiprocessing import shared_memory
import logging
import os

HOST = '127.0.0.1'  # Server's IP address
PORT = 65432        # Port to connect to

margin = 0.025

disp_cam = True

try:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((HOST, PORT))
    print(f"Connected to server at {HOST}:{PORT}")
except Exception as e:
    print("An error occured connecting to the server: ", e)

# Initialize Mediapipe Hands solution
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Setup Webcam
cap = cv2.VideoCapture(0)
# Display window
cv2.namedWindow("Hand Detection", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("Hand Detection", cv2.WND_PROP_TOPMOST, 1)

# Initialize variables for FPS calculation
prev_time = time.time()

# Create or open a shared memory block
shared_memory_name = 'pointer_status'
shared_memory_size = 2

# Create a shared memory block and initialize it to 0
shared_memory = shared_memory.SharedMemory(name=shared_memory_name, create=True, size=shared_memory_size)
shared_memory.buf[0] = 0
shared_memory.buf[1] = 0


# Define the region of interest (ROI) in normalized coordinates for the pointer rectangle
roi = 0.45
roi_x_min = (1.0 - roi) / 2
roi_x_max = roi_x_min + (roi)
roi_y_min = (1.0 - roi) / 2 - 0.2
roi_y_max = roi_y_min + (roi) - 0.2

dir = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(  # Configure logging
    filename=os.path.join(dir, "Gesture.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def show_cam(a):
    global disp_cam
    disp_cam = bool(a)

def distance(a,b):
    length = (b.x-a.x)**2 + (b.y-a.y)**2
    return length

def vector_product(v1, v2):
    """
    Computes the 2D vector cross product of vectors v1 and v2.
    """
    return v1[0] * v2[1] - v1[1] * v2[0]

def is_finger_open(wrist, base, tip):
    """
    Determines if a finger is open or closed regardless of orientation.
    Uses vector mathematics to calculate the relative position of the tip.
    """
    # Compute vectors
    wrist_to_base = (base.x - wrist.x, base.y - wrist.y)
    base_to_tip = (tip.x - base.x, tip.y - base.y)

    # Compute the dot product
    dot_product = wrist_to_base[0] * base_to_tip[0] + wrist_to_base[1] * base_to_tip[1]

    # Finger is open if the vectors point in the same general direction
    return dot_product > 0  # Negative means opposite directions

def is_thumb_open(wrist, base_index, base_thumb, tip_thumb):
    """
    Determines if the thumb is open or closed based on the cross product of vectors.
    """
    # Vector from base_index to base_thumb (reference line)
    base_index_to_base_thumb = (base_thumb.x - base_index.x, base_thumb.y - base_index.y)

    # Vector from base_index to thumb tip
    base_index_to_tip_thumb = (tip_thumb.x - base_index.x, tip_thumb.y - base_index.y)

    # Vector from base_index to wrist
    base_index_to_wrist = (wrist.x - base_index.x, wrist.y - base_index.y)

    # Compute the cross products
    cross_product_tip = vector_product(base_index_to_base_thumb, base_index_to_tip_thumb)
    cross_product_wrist = vector_product(base_index_to_base_thumb, base_index_to_wrist)

    # If the cross products have the same sign, the thumb is open
    # If the cross products have opposite signs, the thumb is closed
    return cross_product_tip * cross_product_wrist < 0

def is_hand_near_edge(hand_landmarks, frame_width, frame_height, margin):
    """
    Determines if any landmark of the hand is near the edge of the frame.
    Returns True if any landmark is too close to the edge (within the margin).
    """
    # Define the safe region with a margin of the frame size
    x_margin = frame_width * margin
    y_margin = frame_height * margin
    
    for landmark in hand_landmarks.landmark:
        # Check if any landmark is within the margin from the edge
        if (landmark.x * frame_width < x_margin or landmark.x * frame_width > frame_width - x_margin or
            landmark.y * frame_height < y_margin or landmark.y * frame_height > frame_height - y_margin):
            return True  # Hand is near the edge
    
    return False  # Hand is within the safe region

with mp_hands.Hands(model_complexity=0, min_detection_confidence=0.7, min_tracking_confidence=0.6) as hands:
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Flip and process the frame
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            # Get frame dimensions
            frame_height, frame_width, _ = frame.shape

            # Initialize list to store the result
            hand_result = [0, False, False, False, False, False]  # Hand type (0/1) + 5 fingers

            # Current time
            current_time = time.time()
            elapsed_time = current_time - prev_time
            prev_time = current_time

            # Calculate FPS
            fps = 1 / elapsed_time if elapsed_time > 0 else 0

            # Convert FPS to integer for display
            fps_text = f"FPS: {int(fps)}"

            # Convert normalized ROI coordinates to pixel values
            roi_top_left = (int(roi_x_min * frame_width), int(roi_y_min * frame_height))
            roi_bottom_right = (int(roi_x_max * frame_width), int(roi_y_max * frame_height))

            pointer_status = bool(shared_memory.buf[0])

            if results.multi_hand_landmarks:
                closest_hand = None
                min_depth = float('inf')  # Initialize with a very large value

                for hand_landmarks, hand_classification in zip(results.multi_hand_landmarks, results.multi_handedness):
                    # Use the wrist landmark (index 0) for depth comparison
                    wrist_depth = hand_landmarks.landmark[0].z

                    if wrist_depth < min_depth:
                        min_depth = wrist_depth
                        closest_hand = (hand_landmarks, hand_classification)

                if closest_hand:
                    # Extract the closest hand's landmarks and classification
                    hand_landmarks, hand_classification = closest_hand

                    # Process the closest hand

                    if distance(hand_landmarks.landmark[0], hand_landmarks.landmark[9]) >= 0.01615975172947892:

                        # Draw a faint box around the margin area (reduced margin size)
                        x_margin = frame_width * margin  # Smaller margin of 5%
                        y_margin = frame_height * margin
                        cv2.rectangle(frame, (int(x_margin), int(y_margin)), 
                                      (frame_width - int(x_margin), frame_height - int(y_margin)), 
                                      (255, 255, 255), 2)  # White color rectangle, thickness=2

                        # Draw ROI rectangle on the frame
                        if pointer_status:  # A flag to indicate pointer mode
                            cv2.rectangle(frame, roi_top_left, roi_bottom_right, (0, 255, 0), 2)

                        # Check if any landmark is near the edge of the frame
                        if is_hand_near_edge(hand_landmarks, frame_width, frame_height, margin):
                            # Skip processing for finger open/close if near edge
                            hand_result[1:] = [False] * 5  # Clear the finger results
                        else:
                            # Determine hand type (left or right)
                            hand_label = hand_classification.classification[0].label
                            is_right_hand = hand_label == "Right"
                            hand_result[0] = 1 if is_right_hand else 0

                            # Extract wrist and finger landmarks
                            wrist = hand_landmarks.landmark[0]
                            finger_tips = [4, 8, 12, 16, 20]
                            finger_bases = [2, 5, 9, 13, 17]

                            # Extract the base of the index finger (landmark 5), base of the thumb (landmark 2), and thumb tip (landmark 4)
                            base_index = hand_landmarks.landmark[7]
                            base_thumb = hand_landmarks.landmark[2]  # Thumb MCP
                            tip_thumb = hand_landmarks.landmark[4]

                            for i in range(5):
                                base = hand_landmarks.landmark[finger_bases[i]]
                                tip = hand_landmarks.landmark[finger_tips[i]]

                                # Use custom logic for thumb
                                if i == 0:
                                    hand_result[i + 1] = is_thumb_open(wrist, base_index, base_thumb, tip_thumb)
                                else:
                                    hand_result[i + 1] = is_finger_open(wrist, base, tip)

                            try:
                                gesture_data = {
                                    "hand_result": hand_result,
                                    "landmarks": [
                                        {"x": landmark.x, "y": landmark.y, "z": landmark.z}
                                        for landmark in hand_landmarks.landmark
                                    ]
                                }

                                # Convert the Python dictionary to a JSON string
                                json_data = json.dumps(gesture_data)

                                # Send the JSON string to the server
                                client_socket.sendall((json_data + "\n").encode('utf-8'))

                            except Exception as e:
                                print(f"Error sending data: {e}")
                                logging.error(f"Client Error: Error sending data: {e}")


                        # Draw landmarks (always display landmarks)
                        mp_drawing.draw_landmarks(
                            frame, 
                            hand_landmarks, 
                            mp_hands.HAND_CONNECTIONS,
                            mp_drawing_styles.get_default_hand_landmarks_style(),
                            mp_drawing_styles.get_default_hand_connections_style()
                        )

            cv2.putText(frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

            if disp_cam:
                # Display the result
                cv2.imshow("Hand Detection", frame)
            
            #show_cam(False)

            if cv2.waitKey(1) and keyboard.is_pressed('ctrl') and keyboard.is_pressed('q'):
                break

    except Exception as e:
        print(f"An Error occured {e}")
        logging.error(f"Client Error: An Error occured {e}")

cap.release()
cv2.destroyAllWindows()
client_socket.close()
shared_memory.close()
shared_memory.unlink()

print("Client Exited Gracefully")