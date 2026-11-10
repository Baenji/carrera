extends Node3D

class_name Track

var track_array: Array[PARTS]

@onready var short_straight_scn = preload("res://track_parts/straight_short.tscn")
@onready var long_straight_scn = preload("res://track_parts/straight.tscn")
@onready var curve_right = preload("res://track_parts/curve_right.tscn")
@onready var curve_left = preload("res://track_parts/curve_left.tscn")
@onready var final_path = $Path3D
@onready var trackParent = $Track

@export var track_loader: TrackLoader


# if reinforcement_learning is active
var RL_MODE := true

var last_connector_point: Vector3 = Vector3.ZERO
var last_rotation_point: Vector3 = Vector3.ZERO

var inner_track_path_points: Curve3D = Curve3D.new()

var track_finished_building: bool = false

# how often to update the signal_rate on the real track car per second
const SIGNAL_RATE_LEVEL_UPDATE_RATE: int = 60.0
var signal_rate_level_update_time: float = 0.0

# signal_rate level correction (a small bias to the signal_rate level so we can correct deviations from the real world car
var signal_rate_level_correction: float = 0.0

enum PARTS {
	NONE, # 0
	FINISH, # 1
	SHORT_STRAIGHT, # 2
	MEDIUM_STRAIGHT, # 3
	LONG_STRAIGHT, # 4
	RIGHT_CURVE, # 5
	LEFT_CURVE, # 6
}

func _ready() -> void:
	track_loader.track_loaded.connect(build_track_from_array)
	NetworkManager.progress.connect(update_tracked_car_progress)
	
func _input(_event: InputEvent) -> void:
	
	if Input.is_action_just_pressed("restart_scene"):
		NetworkManager.reset()
		get_tree().reload_current_scene()
		
	if Input.is_action_just_pressed("ui_right"):
		Engine.time_scale = 0.05
	elif Input.is_action_just_released("ui_right"):
		Engine.time_scale = 1.0
		
	if Input.is_action_just_pressed("start_anyways") and is_instance_valid(track_loader):
		NetworkManager.start_server_debug()
		
		if track_loader.track_loaded.is_connected(build_track_from_array):
			track_loader.track_loaded.disconnect(build_track_from_array)
		build_track_from_array([
			PARTS.FINISH,
			PARTS.LONG_STRAIGHT,
			PARTS.RIGHT_CURVE,
			PARTS.RIGHT_CURVE,
			PARTS.LEFT_CURVE,
			PARTS.LONG_STRAIGHT,
			PARTS.LEFT_CURVE,
			PARTS.RIGHT_CURVE,
			PARTS.RIGHT_CURVE,
			PARTS.LONG_STRAIGHT,
			PARTS.SHORT_STRAIGHT,
			PARTS.RIGHT_CURVE,
			PARTS.LONG_STRAIGHT,
			PARTS.LONG_STRAIGHT,
			PARTS.LONG_STRAIGHT,
			PARTS.RIGHT_CURVE
		])
		
		track_loader.queue_free()

func build_track_from_array(track_order: Array[PARTS]):
	# clear track
	for track_part in trackParent.get_children():
		track_part.queue_free()
	
	########################
	# track order to parts #
	########################
	
	# build the track
	track_finished_building = false
	track_array = track_order
	build_track()
	finish_track()
	print(inner_track_path_points.get_baked_length())

func build_track():
	
	for track in track_array:
		match track:
			PARTS.SHORT_STRAIGHT or PARTS.FINISH:
				var part: TrackPart = short_straight_scn.instantiate()
				trackParent.add_child(part)
				# Set transform
				part.global_transform.origin = last_connector_point
				part.rotation = last_rotation_point

				# Update connector position & rotation
				last_connector_point = part.end_connector.global_position
				last_rotation_point = part.end_connector.global_rotation

				# Append curve
				append_curve(part.inner_path.get_curve(), part.get_global_transform())
				
			PARTS.LONG_STRAIGHT:
				var part: TrackPart = long_straight_scn.instantiate()
				trackParent.add_child(part)
				part.global_transform.origin = last_connector_point
				part.rotation = last_rotation_point

				# Update connector position & rotation
				last_connector_point = part.end_connector.global_position
				last_rotation_point = part.end_connector.global_rotation

				# Append curve
				append_curve(part.inner_path.get_curve(), part.get_global_transform())
				
			PARTS.RIGHT_CURVE:
				var part: TrackPart = curve_right.instantiate()
				trackParent.add_child(part)
				part.global_transform.origin = last_connector_point
				part.rotation = last_rotation_point

				# Update connector position & rotation
				last_connector_point = part.end_connector.global_position
				last_rotation_point = part.end_connector.global_rotation

				# Append curve
				append_curve(part.inner_path.get_curve(), part.get_global_transform())
				
			PARTS.LEFT_CURVE:
				var part: TrackPart = curve_left.instantiate()
				trackParent.add_child(part)
				part.global_transform.origin = last_connector_point
				part.rotation = last_rotation_point

				# Update connector position & rotation
				last_connector_point = part.end_connector.global_position
				last_rotation_point = part.end_connector.global_rotation

				# Append curve
				append_curve(part.inner_path.get_curve(), part.get_global_transform())
				
func append_curve(curve_to_append: Curve3D, point_transform: Transform3D):
	for point_idx in range(curve_to_append.point_count):
		var pos = curve_to_append.get_point_position(point_idx)
		var in_tangent = curve_to_append.get_point_in(point_idx)
		var out_tangent = curve_to_append.get_point_out(point_idx)
		
		# Transform all vectors by the point_transform
		var pos_out = point_transform * pos
		var in_out = point_transform * (pos + in_tangent) - pos_out
		var out_out = point_transform * (pos + out_tangent) - pos_out
		
		inner_track_path_points.add_point(pos_out, in_out, out_out)

func finish_track():
	final_path.curve = inner_track_path_points
	track_finished_building = true

func _physics_process(delta: float) -> void:
	if !track_finished_building:
		return

	# Skip processing if Python is controlling the car during reset
	if NetworkManager.python_reset_mode:
		return
	
	var rl_throttle = 0.0 
	var interp_sim_throttle = 65.0 # can be set to 0-100 for testing
	if RL_MODE:
		rl_throttle = ($Path3D/SimCarModel.target_throttle) # actual values
		interp_sim_throttle = ($Path3D/SimCarModel.throttle) # interpolated values to mimic accel and decel for sim car
		#rl_throttle = min(rl_throttle, 0.8)
		rl_throttle = rl_throttle * 100.0 # estimated 100%
		interp_sim_throttle = interp_sim_throttle * 100.0 # estimated 100%
		
	
	var signal_rate_level = interp_sim_throttle + signal_rate_level_correction

	
	const track_to_sim: float = 3.0 #2.795
	
	$Path3D/SimCarModel.progress += (signal_rate_level * track_to_sim) * delta
	
	# update throttle info
	$Information/VBOX/Throttle/ThrottleInfo.text = str($Path3D/SimCarModel.last_chosen_throttles)
	
	# Update tracked car in TEST_MODE (every frame, not rate-limited)
	if $Path3D/SimCarModel.MANUEL:
		var prog = $Path3D/TrackedCarModel.progress
		prog += (signal_rate_level * track_to_sim) * delta
		update_tracked_car_progress(prog / $Path3D.curve.get_baked_length())
		
	
	# Send signal_rate updates to real track (rate-limited)
	signal_rate_level_update_time += delta
	var step = 1.0 / float(SIGNAL_RATE_LEVEL_UPDATE_RATE)
	if signal_rate_level_update_time > step:
		send_raw_signal_rate(rl_throttle) # remove correction (shouldnt be on track) we calculate from absolute deviation
		signal_rate_level_update_time -= step
		
func update_tracked_car_progress(progress_ratio: float):
	$Path3D/TrackedCarModel.progress_ratio = progress_ratio
	
	# Calculate absolute difference in progress
	var deviation = ($Path3D/TrackedCarModel.progress_ratio - $Path3D/SimCarModel.progress_ratio) * 100.0
	
	# Handle the display
	if $Path3D/SimCarModel.progress_ratio > 0.001:  # Avoid division issues at start
		$Information/VBOX/Deviation/DeviationInfo.text = str(deviation).pad_decimals(2) + "%"
	else:
		$Information/VBOX/Deviation/DeviationInfo.text = "0.00%"
	
	# calculate the signal_rate level correction to minimize deviation
	if deviation > 0.01:
		signal_rate_level_correction += 0.1
	if deviation < -0.01:
		signal_rate_level_correction -= 0.1

	$Information/VBOX/SpeedLevelCorrection/SpeedLevelInfo.text = str(signal_rate_level_correction).pad_decimals(2)


	$Path3D/DeviationMarker.progress_ratio = $Path3D/SimCarModel.progress_ratio
	$Path3D/SimCarModel.progress_ratio = progress_ratio
	
func send_raw_signal_rate(signal_rate_level: float):
	NetworkManager.send_payload({"signal_rate_level": signal_rate_level})
