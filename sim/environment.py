from typing import Optional
import numpy as np
import gymnasium as gym
from gymnasium import spaces
import math

class GridWorldEnv(gym.Env):

    def __init__(self, LAYOUT = {"g R R L G L R R G g R G G G R G"}):

        # Streckensegmente werden durch (Länge, Radius) angegeben
        # Wir haben Lange Gerade (G), kurze Gerade (g), Rechtskurve (R), Linkskurve (L)
        self.TEILE = {
         "G": (342.0, 0.0), "g": (114.0, 0.0),
         "R": (math.pi / 2 * 142.5, 142.5),
         "L": (math.pi / 2 * 199.5, 199.5)
         }

        # Wie schaut unsere Strecke aus basiernd auf den definierten Segmenten in self.TEILE
        self.LAYOUT = LAYOUT 

        # Define what the agent can observe (Input des Netzes)
        # Ende zur aktuellen Kurve, Distanz zur nächsten Kurve, Geschwindigkeit, (vielleicht später noch letzte Aktion)
        # Dict space gives us structured, human-readable observations
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(3,), dtype=np.float32
        )

        # Quasi Output des Netzes
        # Wir brauchen shape(1, ) weil unser Netz am Ende einen Output gibt -> Eine Zahl für den Throttle
        self.action_space = spaces.Box(low=-1, high=1, shape=(1,), dtype=np.float32)

        # Physik Konstanten 
        self.dt = 0.05
        # In der Liste stehen die Konstanten K und T für jeden throttle in der Form (K,T)
        # Für jeden Throttlewert ein Eintrag in der Liste also 100 Werte = 100% 
        self.throttle_consts = [(), ] 

        

