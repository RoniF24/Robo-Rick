# Robo-Rick - Voice and Hand-Gesture Control for an XGO Robot Dog

Robo-Rick is a Python robotics project that combines offline speech recognition and camera-based hand-gesture recognition to control an XGO robot dog. Users can issue English voice commands, switch to hand-follow mode, and guide the robot using hand position and gestures.

## Highlights

- Offline voice recognition with Vosk and a constrained command vocabulary.
- Camera-based hand tracking with MediaPipe and OpenCV.
- Voice and gesture control connected to the robot through `xgolib_dog`.
- Command stabilization across three consecutive frames to reduce jitter.
- A stop interval before switching between movement directions.
- Optional camera debug window when a Linux display is available.
- Audio queue clearing when switching modes to avoid processing stale commands.

## Technologies

Python, Vosk, sounddevice, OpenCV, MediaPipe, XGO robot SDK (`xgolib_dog`), and Linux serial communication. The optional audio scenario uses `mplayer`.

## How It Works

The application starts with the robot asleep. Saying `good morning` enables the robot and voice control. Saying `follow mode` or `switch mode` starts camera-based hand control. A V sign exits hand-follow mode and returns to voice control.

In voice mode, microphone audio is buffered in a queue and processed by a Vosk recognizer. In follow mode, MediaPipe detects hand landmarks; geometric rules classify gestures and convert hand position into robot movement commands.

## Voice Commands

| Command | Behavior |
| --- | --- |
| `good morning` | Wake the robot and enable its motors. |
| `go` | Start moving forward continuously. |
| `walk` / `walk five` | Move forward for a recognized duration; defaults to three seconds. |
| `freeze`, `stand`, `up` | Stop and reset when the voice-mode movement flag is active. |
| `sit` | Move to a configured sitting pose and wait for `good boy` to release it. |
| `hello` | Execute the configured greeting action. |
| `spin` | Execute the configured spin action twice. |
| `pickle` | Run the audio scenario using `pickle.mp3`. |
| `switch mode`, `follow mode`, `follow` | Enter hand-follow mode. |

Duration parsing recognizes one through ten, fifteen, and twenty in English. Other input defaults to three seconds.

## Hand-Gesture Control

| Gesture / position | Behavior |
| --- | --- |
| Open hand in the center | Move forward. |
| Open hand in a side zone | Turn using the mirrored-camera direction mapping. |
| Open hand with fingers pointing down | Move backward. |
| Fist | Stop. |
| No hand detected or unrecognized gesture | Request a stop through the command stabilization logic. |
| V sign | Stop and return to voice mode. |

The image is mirrored before processing. Side zones occupy the outer 40% of the frame on each side. Commands become stable after three consecutive matching frames. Changes between movement commands include a 0.5-second stop interval.

## Repository Files

| File | Purpose |
| --- | --- |
| `voiceV7_main.py` | Robot initialization, audio capture, speech recognition, voice actions, and mode switching. |
| `follow_mode.py` | Camera capture, hand tracking, gesture classification, command stabilization, and robot movement. |
| `pickle.mp3` | Audio used by the optional `pickle` scenario. |

## Hardware and Environment

This project requires compatible XGO hardware and its Python SDK; it is not a standalone desktop simulation.

- XGO robot dog supported by `xgolib_dog.XGO_DOG`.
- Linux robot environment with serial access; the current code uses `/dev/ttyAMA0`.
- Camera accessible through OpenCV camera index `0`.
- Microphone supporting the configured 16 kHz, mono, 16-bit stream.
- A compatible English Vosk model extracted into a local directory named `model`.
- Speaker and `mplayer` for the optional audio scenario; the current code selects ALSA device `hw=1.0`.

The Vosk model and robot SDK are not included in this repository. Install the robot SDK using the instructions for your hardware. MediaPipe must provide the `mp.solutions.hands` API used by the code; choose dependency versions compatible with your robot's Python version and architecture.

## Setup

Clone the repository on the robot's Linux environment:

```bash
git clone https://github.com/RoniF24/Robo-Rick.git
cd Robo-Rick
```

Install the Python libraries in a suitable environment:

```bash
python3 -m pip install vosk sounddevice opencv-python mediapipe
```

Install any platform-specific audio/video prerequisites and the XGO SDK separately. Place an English Vosk model in `model/`, and confirm that the camera, microphone, serial port, and optional playback device match the settings in the source files. The repository does not currently include a pinned dependency file.

Run from the repository root so relative model and audio paths resolve:

```bash
python3 voiceV7_main.py
```

Say `good morning`, then a voice command. Say `follow mode` to start gesture control and make a V sign to return. Use `Ctrl+C` to exit. In follow mode, `q` also exits when the debug window is available.

## Current Limitations

- Several actions use blocking waits. Voice commands are not processed continuously during timed walking, predefined actions, the audio scenario, or the sitting loop.
- The sitting loop listens for `good boy` rather than the normal command vocabulary.
- Voice checking inside the follow-mode camera loop is currently commented out. Use the V sign to return to voice mode.
- Sleep handling checks for `good night`, while the constrained recognizer vocabulary includes `night`; this mismatch needs correction before documenting sleep as a reliable voice command.
- Robot action IDs, sitting angles, serial port, and audio device settings are hardware-specific.
- Gesture recognition depends on camera visibility and landmark quality. The stop behaviors are implementation features, not a guarantee of immediate stopping.
- No obstacle avoidance or autonomous navigation is implemented in these files.

Run hardware demonstrations in a clear space with a physical way to stop or power down the robot. Dependency installation and hardware execution have not been validated as part of this documentation review.
