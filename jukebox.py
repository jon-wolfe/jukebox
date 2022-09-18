import time
from huesdk import Hue
from random import randint
import RPi.GPIO as GPIO
import yaml
GPIO.setmode(GPIO.BCM)

# Load secrets from config file
with open("config.yaml","r") as configfile:
    config = yaml.load(configfile, Loader=yaml.Loader)

# Connect to our bridge
hue = Hue(bridge_ip=config["hue_ip"], username=config["hue_username"])
lights = hue.get_lights()

# Save all current light colors
# NOTE: This can be inaccurate.  AppleTV maybe doesn't update Hue Bridge?
def read_hue(lights):
    print("Remembering existing light colors")
    old_hls = {}
    for light in lights:
        old_hls[light.id_] = (light.hue, light.bri, light.sat)
    print("  Gathered")
    return old_hls
orig_hls = read_hue(lights)

# Restore a set of lights using a dicts of id->(H,L,S)
def write_hue(lights, id_to_hls):
    # Restore original colors
    for light in lights:
        hls = id_to_hls[light.id_]
        light.set_color(hue=hls[0])  
        light.set_brightness(hls[1])  
        light.set_saturation(hls[2]) 

# These default colors were chosen by my 8yo son to look like minecraft
def randomize_a_hue(light, H=(17000,25000), L=(5,254), S=(254,254)):
    # Set a light to a random color
    light.set_color(hue=randint(*H))
    light.set_brightness(randint(*L))
    light.set_saturation(randint(*S))
    


def randomize_each_hue(lights, H=(17000,25000), L=(5,254), S=(254,254)):
    # Set all lights once to a random color
    for light in lights:
        randomize_a_hue(light, H,L,S)
    
def randomize_random_hue(lights, H=(17000,25000), L=(5,254), S=(254,254), count=100):
    # Find all valid ids
    valid_ids = []
    for light in lights:
        valid_ids.append(light.id_)
        
    # Randomly pick lights and rerfesh
    for i in range(count):
        lightnum = randint(0,len(valid_ids)-1)
        light = hue.get_light(id_=valid_ids[lightnum])
        randomize_a_hue(light, H,L,S)

#############
# Pins for all JukeBox relays, buttons, etc.
relay_right = 19
relay_left = 20
relay_lights = 12
relay_laser = 16
relay_fog = 6
power_fog = 17

switch_quarter = 1

bank_a = 23
bank_b = 22
pull = 0
button_v = 4
button_w = 27
button_x = 21
button_y = 13
button_z = 26

#############
# Setup all inputs and outputs
GPIO.setup(relay_left, GPIO.OUT)
GPIO.setup(relay_right, GPIO.OUT)
GPIO.setup(relay_laser, GPIO.OUT)
GPIO.setup(relay_lights, GPIO.OUT)
GPIO.setup(relay_fog, GPIO.OUT)
GPIO.setup(power_fog, GPIO.OUT)

GPIO.setup(switch_quarter, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# The 20x 0-9 and A-H buttons use a drive/read
#   multiplexing scheme
GPIO.setup(bank_a, GPIO.OUT)
GPIO.setup(bank_b, GPIO.OUT)
GPIO.setup(pull, GPIO.OUT)

GPIO.setup(button_v, GPIO.IN)
GPIO.setup(button_w, GPIO.IN)
GPIO.setup(button_x, GPIO.IN)
GPIO.setup(button_y, GPIO.IN)
GPIO.setup(button_z, GPIO.IN)

# Set everything to nominal
GPIO.output(relay_laser, False)
GPIO.output(relay_lights, True)
GPIO.output(relay_left, False)
GPIO.output(relay_right, False)

# Warmup the fog machine
print("Disabling the Fog machine.  (Break here to keep off).")
GPIO.output(power_fog, False)
time.sleep(2)
print("Preparing to Warmup Fog")
GPIO.output(power_fog, True)

# True if a quarter is currently flying through the coin-slot (brief!)
def see_quarter():
    return GPIO.input(switch_quarter)

# Turn on (or off) the laser
def do_laser(on=True):
    GPIO.output(relay_laser, on)

# Turn on (or off) the main white JukeBox lights
def do_lights(on=True):
    GPIO.output(relay_lights, not on)

# Make the lights "cold start" like an old fluorescent
def sputter_lights():
    do_lights()
    time.sleep(0.05)
    do_lights(False)
    time.sleep(0.1)
    do_lights()
    time.sleep(0.15)
    do_lights(False)
    time.sleep(0.2)
    do_lights()

# Run the fog for a short time (or forever? >@_@< )
def do_fog(duration=2, forever=False):
    GPIO.output(relay_fog, True)
    time.sleep(duration)
    if forever:
        return
    GPIO.output(relay_fog, False)
    time.sleep(3)
    


    
    
# Do a mini-show (demo) when a quarter is inserted
while True:
    print("KIDS RULE ADULTS DROOL!!!")
    print("Ready for quarter")
    while not see_quarter():
        continue
    sputter_lights()
    do_fog(3)
    randomize_each_hue(lights)
    do_laser()
    randomize_random_hue(lights)
    time.sleep(6)
    do_laser(False)
    do_lights(False)
    write_hue(lights, orig_hls)

GPIO.cleanup()
exit(0)
