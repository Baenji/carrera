extends "res://Tracks/track_builder_2/racecar_base.gd"

# Extends base racecar with camera-based off-track detection and auto-reset

# Camera reset state tracking
var waiting_for_reset = false
var reset_requested_from_camera = false

func _ready() -> void:
	super._ready()
	
	# Connect to NetworkManager signals for camera-based detection
	NetworkManager.crash_detected.connect(_on_crash_detected)
	NetworkManager.reset_complete.connect(_on_reset_complete)

func is_processing_blocked() -> bool:
	"""Block physics processing while waiting for camera-based reset"""
	return waiting_for_reset

# ============================================================================
# CAMERA-BASED OFF-TRACK DETECTION INTEGRATION
# ============================================================================

func _on_crash_detected(crash: bool):
	"""Called when camera detects off-track event
	
	This is triggered by the Python camera system when it detects the car
	has gone off-track or crashed. The episode is terminated and we wait
	for the auto-reset system to reposition the car.
	"""
	print("🚨 Episode terminated by camera: " + str(crash))
	
	# Mark that we're waiting for reset
	waiting_for_reset = true
	reset_requested_from_camera = true
	
	# Give negative reward for going off-track
	give_reward(-10.0)
	
	# Terminate the current episode
	rl.done = true
	rl.needs_reset = true
	
	# Note: DO NOT call reset() here - wait for camera to complete auto-positioning

func _on_reset_complete(_reset: bool):
	"""Called when camera completes auto-repositioning
	
	The camera system has driven the car back to the start position.
	Now we can actually reset the Godot simulation state.
	"""
	print("✅ Camera reset complete - resetting episode")
	
	# Now safe to reset
	waiting_for_reset = false
	reset_requested_from_camera = false
	
	# Call base reset
	super.reset()
