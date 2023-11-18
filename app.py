from flask import Flask, render_template, Response
import cv2
import face_recognition
import pickle
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import datetime
from collections import defaultdict

app = Flask(__name__)

# Load face encodings from the binary file
with open("face_enc", 'rb') as file:
    data = pickle.load(file)

known_face_names = data['names']
known_face_encodings = data['encodings']
attendance_records = {}

# Initialize some variables
video_capture = cv2.VideoCapture(0)


def initialize_firebase():
    # Initialize Firebase
    cred = credentials.Certificate(
        'ventura-dc607-firebase-adminsdk-cps1w-2ca89dc469.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ventura-dc607-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })

initialize_firebase()

def recognize_faces(frame):
    # Find all face locations and face encodings in the current frame
    face_locations = face_recognition.face_locations(frame)
    face_encodings = face_recognition.face_encodings(frame, face_locations)

    # Loop through each face found in the frame
    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        # Check if the face matches any known faces
        matches = face_recognition.compare_faces(
            known_face_encodings, face_encoding)

        name = "Unknown"

        # If a match is found, use the name of the first matching known face
        if True in matches:
            first_match_index = matches.index(True)
            name = known_face_names[first_match_index]
            mark_attendance(name)

        # Draw rectangle and display the name on the screen
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, bottom - 6),
                    font, 0.5, (255, 255, 255), 1)

    return frame


def generate_frames():
    while True:
        success, frame = video_capture.read()
        if not success:
            break
        else:
            frame = recognize_faces(frame)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def update_attendance_records(current_date, name):
        if name not in attendance_records:
            attendance_records[name] = [current_date]
        else:
            dates = attendance_records[name]
            if current_date not in dates:
                dates.append(current_date)

def mark_attendance(name):
    print("Marking Attendance")
    # Check if the year, month, and day nodes exist in Firebase
    now = datetime.datetime.now()
    year = now.strftime('%Y')
    month = now.strftime('%B')
    day = now.strftime('%d')

    ref = db.reference(f'/attendance/{year}/{month}')
    if not ref.get():
        ref.set({})

    ref_day = ref.child(day)
    if not ref_day.get():
        print('Not ref_day')
        ref_day.set({})

    # Check if the person is already present in the day's attendance
    person_ref = ref_day.child(name)
    person_data = person_ref.get()
    print("person_data",person_data)

    if person_data:
        # Get the last entry's timestamp
        last_entry = list(person_data.values())[-1]
        last_entry_timestamp = datetime.datetime.strptime(
            last_entry['date'], "%y/%m/%d %H:%M:%S")

        # Calculate the time difference between now and the last entry
        time_difference = now - last_entry_timestamp

            # Check if the time difference is less than 10 minutes
        if time_difference.seconds < 60:
            print(f"Skipping 'Clock Out' for {name}.")
            return

        # If it's been more than 10 minutes, mark 'Clock Out'
        status = 'Clock Out'
    else:
        # If there are no previous entries, mark 'Clock In'
        status = 'Clock In'

        # Store attendance data in Firebase
    attendance_data = {
        'date': now.strftime("%y/%m/%d %H:%M:%S"),
        'name': name,
        'status': status
    }
    person_ref.push(attendance_data)

    update_attendance_records(now.strftime("%y_%m_%d"), name)

        # # Voice announcement
        # announcement = f"{name}!"
        # self.announce(announcement)


def consolidate_attendance():
    now = datetime.datetime.now()
    year = now.strftime('%Y')
    month = now.strftime('%B')
    day = now.strftime('%d')

    ref = db.reference(f'/attendance/{year}/{month}')
    attendance_data = ref.get()

    consolidated_data = defaultdict(list)
    for day_data in attendance_data.values():
            for name, records in day_data.items():
                for key, data in records.items():
                    date = data['date']
                    status = data['status']
                    consolidated_data[name].append((date, name, status))

    consolidated_attendance = []
    for name, records in consolidated_data.items():
            clock_in_record = records[0]
            clock_out_records = records[1:]
            consolidated_attendance.append(clock_in_record)
            consolidated_attendance.extend(clock_out_records)

    consolidated_ref = db.reference(f'/consolidated_attendance/{year}/{month}')
    consolidated_ref.set(consolidated_attendance)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    app.run(debug=True)
