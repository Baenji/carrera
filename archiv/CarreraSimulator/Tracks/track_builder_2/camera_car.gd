extends Camera3D

@export var cam_pivot: Node3D
@export var overhead: bool = true

var initial_position: Vector3
var initial_rotation: Vector3

const SPEED = 30.0

func _ready() -> void:
	initial_position = self.global_position
	initial_rotation = self.global_rotation

func _input(event: InputEvent) -> void:
	if Input.is_action_just_pressed("overhead_cam"):
		overhead = !overhead

func _physics_process(delta: float) -> void:
	
	var target_position : Vector3 = cam_pivot.global_position
	var target_rotation : Vector3 = cam_pivot.global_rotation
	
	if overhead:
		target_position = initial_position
		target_rotation = initial_rotation
	
	self.global_position = lerp(self.global_position, target_position, SPEED * delta)
	
	self.global_rotation.x = lerp_angle(self.global_rotation.x, target_rotation.x, SPEED * delta)
	self.global_rotation.y = lerp_angle(self.global_rotation.y, target_rotation.y, SPEED * delta)
	self.global_rotation.z = lerp_angle(self.global_rotation.z, target_rotation.z, SPEED * delta)
