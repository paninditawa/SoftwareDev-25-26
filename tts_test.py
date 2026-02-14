import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pygame
import pyttsx3
import sys

pygame.mixer.quit()
pygame.init()
screen = pygame.display.set_mode((400, 200))
pygame.display.set_caption("PyGame + TTS test")

engine = pyttsx3.init(driverName='sapi5')
engine.setProperty("rate", 180)

def speak(text):
    engine.say(text)
    engine.runAndWait()

speak("Test. If you hear this, text to speech is working before the loop.")

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                print("LEFT pressed")
                speak("Left")
            elif event.key == pygame.K_RIGHT:
                print("RIGHT pressed")
                speak("Right")

    pygame.time.wait(20)