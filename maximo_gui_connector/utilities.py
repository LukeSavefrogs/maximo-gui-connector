from collections import namedtuple

def namedEnum(**kwargs):
	"""From a dict / keyword args

	Usage: 

		Keyworded params: 
			enum(Apple="Steve Jobs", Peach=1, Banana=2)
		
		Dictionary param: 
			values = {"Salad": 20, "Carrot": 99, "Tomato": "No i'm not"} 
			enum(**values)

	Returns:
		Enum: The enum object containing all the provided values
	"""
	return namedtuple('Enum', kwargs.keys())(*kwargs.values())