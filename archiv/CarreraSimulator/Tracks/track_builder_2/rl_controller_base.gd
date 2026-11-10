extends AIController3D

var throttle: float = 0.0
var last_progress: float = 0.0
var progress: float = 0.0
var throttle_values = [0.0, 0.5, 0.70]

@onready var racecar = $".."

func _physics_process(delta):
	#reward -= delta

	n_steps += 1
	if n_steps > reset_after:
		racecar.game_over(0)
	

func get_obs() -> Dictionary:
	return {"obs": [
		racecar.discrete_progress_ratio,
		racecar.is_out,
		racecar.discrete_velocity
	]}


func get_reward() -> float:
	return reward


func get_action_space() -> Dictionary:
	return {
		"throttle": {"size": 1, "action_type": "continuous"},
	}


func set_action(action) -> void:
	#var idx = action["throttle"]        # 0–4
	#throttle = throttle_values[idx] # maps to 0–1.0 in 0.25 steps
	throttle = abs(action["throttle"][0])
