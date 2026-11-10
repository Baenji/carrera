extends AIController3D

var throttle: float = 0.0
var last_progress: float = 0.0
var progress: float = 0.0

@onready var racecar = $".."

func _physics_process(delta):
	# compute progress
	progress = sign(racecar.progress_ratio - last_progress)
	last_progress = progress
	
	#reward += progress * delta
	#reward -= delta

	n_steps += 1
	if n_steps > reset_after:
		racecar.game_over(0)
	

func get_obs() -> Dictionary:
	return {"obs": [
		racecar.progress_ratio
	]}


func get_reward() -> float:
	return reward


func get_action_space() -> Dictionary:
	return {
		"throttle": {"size": 1, "action_type": "continuous"},
	}


func set_action(action) -> void:
	throttle = action["throttle"][0]
