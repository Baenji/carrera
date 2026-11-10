extends PathFollow3D

const THROTTLE_ACCEL : float = 1.0
const THROTTLE_DEACCEL : float = 3.0
const MAX_SPEED : float = 6.9 # m/s = 25 km/h
const DRAG_SENSITIVITY : float = 12.0

const CRASH_REWARD = -20.0

var throttle: float = 0.0
var prev_pos: Vector3
var is_out: bool = false
var crash_played: bool = false

var last_progress = 0.0

var lap_time = 0.0
var best_time = 1000.0

var crash_detected = false

@onready var rl = $AIController3D

func _ready() -> void:
	prev_pos = global_position
	NetworkManager.crash_detected.connect(crash_detected)

func _physics_process(delta: float) -> void:
	
	if rl.needs_reset:
		game_over()
	
	# --- User Throttle logic ---
	if Input.is_action_pressed("ui_accept"):
		
		var accel = delta * THROTTLE_ACCEL
		
		if Input.is_action_pressed("ui_up"):
			accel = delta * 3.0 * THROTTLE_ACCEL
		
		throttle = lerp(throttle, 1.0, accel)
	else:
		throttle = lerp(throttle, 0.0, delta * THROTTLE_DEACCEL)
	
	throttle = abs(rl.throttle)

	# detect laps
	var lap_progress = progress_ratio
	
	lap_time += delta
	
	if (last_progress - lap_progress) > 0.99:
		# lap!
		#rl.reward += 10
		print("LAP DONE with time " + str(lap_time))
		
		var reward = clamp(exp(best_time / lap_time)-1.0, -1.0, 100.0)
		
		if lap_time > 1.0 and lap_time < best_time:
			best_time = lap_time
			print("NEW BEST TIME FOR this node: " + str(best_time))
		
		game_over(reward)
	
	last_progress = lap_progress

	# --- Velocity + side drag measurement ---
	var current_pos = global_position
	var velocity = (current_pos - prev_pos) / delta
	prev_pos = current_pos

	var forward = transform.basis.z.normalized()
	var right = transform.basis.x.normalized()

	var forward_speed = velocity.dot(forward)
	var sideways_speed = velocity.dot(right)
	var side_drag = abs(sideways_speed)
	

	if side_drag > DRAG_SENSITIVITY:
		is_out = true
		#print("💨 Goofy drift! Side drag =", side_drag)
	
	var _speed = throttle * MAX_SPEED
	
	if !is_out:
		progress += delta * _speed * 5.26
	else:
		game_over(CRASH_REWARD)
		
	if crash_detected:
		game_over(CRASH_REWARD)
				
func game_over(reward = 0.0):
	rl.done = true
	rl.reward += reward
	rl.reset()
	lap_time = 0.0
	reset()

func reset():
	last_progress = 0.0
	rl.last_progress = 0.0
	progress_ratio = 0.0
	is_out = false
