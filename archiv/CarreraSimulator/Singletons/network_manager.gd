extends Node

const INFO_PORT := 11360
const DEBUG_PORT := 11361
var server := TCPServer.new()
var client: StreamPeerTCP

var SIMULATION_MODE: bool = true # if set to true, everything except the track order gets ignored
var SKIP_START_SCREEN: bool = false

signal track_order(track_array: Array)
signal progress(progress_ratio: float)
signal crash_detected(crash_detected: bool)
signal reset_complete(reset_complete: bool)

# Track whether Python is in reset mode (controls Arduino directly)
var python_reset_mode: bool = false

func _ready() -> void:

	var arguments = {}
	for argument in OS.get_cmdline_args():
		if argument.contains("="):
			var key_value = argument.split("=")
			arguments[key_value[0].trim_prefix("--")] = key_value[1]
		else:
			# Options without an argument will be present in the dictionary,
			# with the value set to an empty string.
			arguments[argument.trim_prefix("--")] = ""

	if 'sim' in arguments.keys():
		# ignore everything from camera except track order
		SIMULATION_MODE = true
		print("STARTING IN SIMULATION MODE. IGNORING ALL RL CAMERA INSTRUCTIONS")
	else:
		print("STARTING IN RL MODE")
		
	if 'skip_start_screen' in arguments.keys():
		# Skip the wait for track order and start with hardcoded track (important for headless envs)
		SKIP_START_SCREEN = true
		SIMULATION_MODE = true
		print("SKIPPING START SCREEN")
		return
	else:
		start_server_info()
	
	
func start_server_info():
	if SKIP_START_SCREEN:
		return
	start_socket(INFO_PORT)
	
func start_server_debug():
	if SKIP_START_SCREEN:
		return
	
	reset()
	start_socket(DEBUG_PORT)
	
func start_socket(port):
	# PORT FOR INFORMATION LIKE TRACK 
	var err = server.listen(port)
	if err != OK:
		push_error("Failed to start server: %s" % err)
		return
	print("Listening for Python on port %d" % port)

	
func reset():
	
	if server.is_listening():
		server.stop()
	
	if client and client.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		client.disconnect_from_host()
		
	if client:
		client = null

func _process(_delta):

	
	# 1. Verbindung akzeptieren
	if not client and server.is_connection_available():
		client = server.take_connection()
		print("Python connected!")

	# 2. Daten empfangen und parsen
	if client and client.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		if client.get_available_bytes() > 0:
			var msg = client.get_utf8_string(client.get_available_bytes())
			var splitmsg = msg.split("}", false)
			for insidemsg in splitmsg:
				var parse_msg = insidemsg + "}"
				handle_msg(parse_msg)
	elif SKIP_START_SCREEN:
		handle_msg(JSON.stringify({"track_order": [1, 4, 5, 5, 6, 4, 6, 5, 5, 4, 2, 5, 4, 4, 4, 5]}))

func handle_msg(message):
	var result = JSON.parse_string(message)
	if result is Dictionary: # Sicherstellen, dass das Parsen erfolgreich war
		# Track Order (track parts in order)
		if result.has("track_order") and result["track_order"] is Array:
			track_order.emit(result["track_order"])
			
		if SIMULATION_MODE:
			return # ignore everything underneath trackorder
			
		# Progress (of car around the track in percent)
		if result.has("progress") and result["progress"] is float:
			progress.emit(result["progress"])
			
		if result.has("crash_detected") and result["crash_detected"] is bool:
			crash_detected.emit(result["crash_detected"])
			python_reset_mode = result["crash_detected"]  # Enter reset mode
		
		if result.has("reset_complete") and result["reset_complete"] is bool:
			reset_complete.emit(result["reset_complete"])
			python_reset_mode = false  # Exit reset mode
			print("✅ Python reset complete - model takes over")


func send_payload(payload: Dictionary):
	if not client or client.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		#push_error("No active client connection.")
		return
	
	var json_str = JSON.stringify(payload)
	var bytes = json_str.to_utf8_buffer()
	
	var sent = client.put_data(bytes)
	if sent != OK:
		push_error("Failed to send data: %s" % sent)
	else:
		print(json_str)
