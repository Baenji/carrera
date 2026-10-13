extends Node

class_name TrackLoader

# Das Signal, das das Array mit der Streckenreihenfolge (track_order) enthält.
signal track_loaded(track_order: Array) 

func _ready():
	NetworkManager.track_order.connect(handle_track_order)

func handle_track_order(track_order_array):	
	var final_track_order : Array[Track.PARTS] = []
	
	for item in track_order_array:
		final_track_order.append(int(item))
		
	# send track order to subscribers 
	print("TRACK WAS LOADED: " + str(final_track_order))
	emit_signal("track_loaded", final_track_order) 
	
	self.queue_free()
