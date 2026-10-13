extends PathFollow3D

const THROTTLE_ACCEL : float = 20.0
const THROTTLE_DEACCEL : float = 5.0
#const MAX_SPEED : float = 6.9 # m/s = 25 km/h
const DRAG_SENSITIVITY : float = 17.5 # calibrated for round about 50 threshold
const DRAG_CRASH_FRAMES_NEEDED: int = 3.0 # how many frames over the threshold

var drag_crash_frames = 0.0

var highest_drag : Array = []

var throttle: float = 0.0
var target_throttle: float = 0.0
var last_chosen_throttles: Array[float] = [0.0, 0.0, 0.0] # for a quick history
var velocity: Vector3
var prev_pos: Vector3
var is_out: bool = false
#var crash_played: bool = false

var last_progress = 0.0
var half_time = false

var lap_time = 0.0
var best_time = 1000.0

var our_reward = 0.0
var our_round_reward = 0.0

var discrete_progress_ratio = 0.0
var discrete_progress_ratio_step_size = 5.0
var discrete_velocity = 0.0
var discrete_velocity_step_size = 2.0

var MANUEL = false
var MANUEL_SPEED: float = 0.55

@onready var rl = $AIController3D

func _ready() -> void:
	prev_pos = global_position

func is_processing_blocked() -> bool:
	"""Virtual method - override in subclasses to block physics processing"""
	return false

func _physics_process(delta: float) -> void:
	if is_processing_blocked():
		return
	
	discrete_progress_ratio = floor(self.progress_ratio / discrete_progress_ratio_step_size) * discrete_progress_ratio_step_size
	discrete_velocity = floor(self.velocity.length() / discrete_velocity_step_size) * discrete_velocity_step_size
	
	%RewardInfo.text = str(our_reward)
	%RoundRewardInfo.text = str(our_round_reward)
	
	target_throttle = rl.throttle
	
	if MANUEL:
		target_throttle = float(Input.is_action_pressed("ui_accept")) * MANUEL_SPEED
	
	
	#if rl.needs_reset:
	#	game_over()
	#if last_chosen_throttles[0] != target_throttle: # only use different values, not really correct
	last_chosen_throttles.push_front(target_throttle)
	while last_chosen_throttles.size() > 3:
		var _d = last_chosen_throttles.pop_back()
		

	# THROTTLE ITSELF IS SENT TO THE REAL TRACK, DONT TOUCH!
	if target_throttle > throttle:
		throttle = lerp(throttle, target_throttle, clampf(0.0, THROTTLE_ACCEL * delta, 1.0))
	else:
		throttle = lerp(throttle, target_throttle, clampf(0.0, THROTTLE_DEACCEL * delta, 1.0))


	# detect laps
	var lap_progress: float = progress_ratio
	
	lap_time += delta
	
	# half time segment
	if (lap_progress > 0.4 and lap_progress < 0.8):
		half_time = true
	
	
	if ((last_progress - lap_progress) > 0.95 and half_time == true):
		# lap!
		#rl.reward += 10
		half_time = false
		print("====================================================================")
		print("LAP DONE with time " + str(lap_time) + " ; CURRENT BEST TIME IS " + str(best_time))
		
		var reward = clamp(exp(best_time / lap_time)-1.0, -1.0, 100.0)
		
		if lap_time < best_time + 0.1:
			give_reward(1.0)
			print("little bonus")
		
		if lap_time > 0.05 and lap_time < best_time:
			best_time = lap_time
			print("NEW BEST TIME: " + str(best_time))
			game_over(10.0) # lets see
		elif lap_time > 0.05:
			#round_reward = reward - 1.82
			#print("GAVE ROUND REWARD: " + str(round_reward))
			game_over(0.1)
		
		
		
		print("ROUND REWARD: " + str(our_round_reward+0.1))
		our_round_reward = 0.0
		lap_time = 0.0
		game_over(0.01)
		
	
	last_progress = lap_progress

	# --- Velocity + side drag measurement ---
	var current_pos = global_position
	velocity = (current_pos - prev_pos) / delta
	prev_pos = current_pos
	
	# give small reward for high throttle
	# [0.0, 0.35, 0.5, 0.6, 0.75]

	if throttle >= 0.75:
		give_reward(0.001 * delta)
	if throttle >= 0.6:
		give_reward(-0.005 * delta) # was -0.003
	elif throttle >= 0.5:
		give_reward(-0.01 * delta)
	elif throttle >= 0.45:
		give_reward(-0.02 * delta)
	else:
		give_reward(-0.03 * delta) # break
		
	#give_reward(progress_ratio * delta / 100.0)
	


	var forward = transform.basis.z.normalized()
	var right = transform.basis.x.normalized()

	var forward_speed = velocity.dot(forward)
	var sideways_speed = velocity.dot(right)
	var side_drag = abs(sideways_speed)

	if side_drag > DRAG_SENSITIVITY and NetworkManager.SIMULATION_MODE:
		drag_crash_frames = clamp(drag_crash_frames + 1, 0, DRAG_CRASH_FRAMES_NEEDED)
		print(drag_crash_frames)
	else:
		drag_crash_frames = clamp(drag_crash_frames - 1, 0, DRAG_CRASH_FRAMES_NEEDED)
	
		
	if drag_crash_frames >= DRAG_CRASH_FRAMES_NEEDED:
		is_out = true
		game_over(-5.0)
		print("💨 Crash! Side drag =", side_drag)

	#var _speed = throttle * MAX_SPEED
	
	#if !is_out:
	#	progress += delta * _speed * 5.26
				
func give_reward(reward: float = 0.0):
	our_round_reward += reward
	#rl.done = true
	rl.reward += reward
	#print("Reward: " + str(reward))
	#rl.reset()
	#lap_time = 0.0
	#reset()
	
func game_over(reward: float = 0.0):
	our_round_reward += reward
	rl.done = true
	rl.reward += reward
	print("Reward: " + str(rl.reward))
	rl.reset()
	lap_time = 0.0
	reset()

func reset():
	#return # reset isnt supposed to do anything while the real car is present
	last_progress = 0.0
	rl.last_progress = 0.0
	our_round_reward = 0.0
	half_time = false
	last_chosen_throttles = [0.0, 0.0, 0.0]
	
	if NetworkManager.SIMULATION_MODE:
		progress_ratio = 0.0
		
	%TrackedCarModel.progress_ratio = 0.0
	is_out = false
