import numpy as np
import gymnasium as gym
from gymnasium import spaces
import math

class CarreraEnv(gym.Env):

    def __init__(self, layout: str = "g R R L G L R R G g R G G G R G"):
        
        # Streckensegmente werden durch (Länge, Radius) angegeben
        # Wir haben Lange Gerade (G), kurze Gerade (g), Rechtskurve (R), Linkskurve (L)
        self.TEILE = {
         "G": (342.0, 0.0), "g": (114.0, 0.0),
         "R": (math.pi / 2 * 142.5, 142.5),
         "L": (math.pi / 2 * 199.5, 199.5)
         }

        # Wie schaut unsere Strecke aus basiernd auf den definierten Segmenten in self.TEILE
        self.LAYOUT = layout.split() 

        # Streckengeometrie einmal vorberechnen
        self.seg_len   = np.array([self.TEILE[t][0] for t in self.LAYOUT])
        self.is_curve  = np.array([self.TEILE[t][1] > 0 for t in self.LAYOUT])
        self.seg_start = np.concatenate([[0.0], np.cumsum(self.seg_len)[:-1]])
        self.seg_end   = self.seg_start + self.seg_len
        self.track_len = self.seg_len.sum()

        # Stateparameter initialisieren -  wird in reset() auf Zufall gesetzt werden
        self._pos = 0.0
        self._dst_curve_end = 0.0 
        self._dst_next_curve = 0.0 
        self._speed = 0.0 

        # Define what the agent can observe (Input des Netzes)
        # Ende zur aktuellen Kurve, Distanz zur nächsten Kurve, Geschwindigkeit, (vielleicht später noch letzte Aktion)
        # Box-Space: 3 normierte Werte zwischen 0 und 1
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(3,), dtype=np.float32
        )

        # Quasi Output des Netzes
        # Wir brauchen shape(1, ) weil unser Netz am Ende einen Output gibt -> Eine Zahl für den Throttle
        self.action_space = spaces.Box(low=-1, high=1, shape=(1,), dtype=np.float32)

        # Physik Konstanten 
        self.dt = 0.05 # TODO: Wert berichtigen
        self.v_max = 3000 # Maximal Geschwindigkeit die das Auto erreichen kann #TODO: Wert berichtigen
        self.d_max = 1200 # Wie hoch die Distanz zur nächsten Kurve maximal sein kann # TODO: Wert berichtigen
        self.v_crash = 1300 #TODO: Berichtigen ->Kurvenaustrittsgeschwindigkeit muss gemessen werden
        # In der Liste stehen die Konstanten K und T für jeden throttle in der Form (K,T)
        # Ein Eintrag pro Throttlewert 0..100 -> 101 Einträge
        # Schätzung: unter 10 % Totzone (Auto bewegt sich nicht), darüber linear bis v_max; T ca. 0.4 s
        # -> durch Messungen ersetzen
        self.throttle_consts = [
            (0.0 if p < 10 else self.v_max * (p - 10) / 90, 0.4)
            for p in range(101)
        ]
 

    def _get_obs(self):
        obs = np.array([
            self._dst_curve_end / self.d_max, 
            self._dst_next_curve / self.d_max, 
            self._speed / self.v_max
        ], dtype=np.float32) 
        return np.clip(obs, 0.0, 1.0) # Begrenz jeden Wert im Array auf den Berich zwischen 0 und 1 -> Werte kleiner 0 werden 0 und Werte größer 1 werden 1

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Track len enthält die gesammtlänge der Strecke 
        # np_random.uniform setzt die pos gleichverteilt auf Werte in diesem Wertebereich
        # über np.searchsorted lässt sich später wieder auf das tatsächliche streckensegment schließen
        self._pos = self.np_random.uniform(0, self.track_len)

        # Eine zufällige Geschwindigkeit zwischen 0 und der Maximalgeschwindigkeit zum Start wählen
        self._speed = self.np_random.uniform(0.0, self.v_max)
        self._update_distances()
        self.step_count = 0
        return self._get_obs(), {}

    def _update_distances(self):
        idx = int(np.searchsorted(self.seg_start, self._pos, side="right") - 1) # Aus der Position wird das Segment herausgefunden
        rest = self.seg_end[idx] - self._pos # Wie viel Distanz bleibt auf dem Segement übrig

        # Wenn wir in einer Kurve sind können wir die distanz zum Kurvenende bestimmen
        if self.is_curve[idx]:
            self._dst_curve_end = rest

        else: # Hier sind wir auf einer Geraden -> distanz zu kurvenende ist daher 0 
            # relevant ist nur die Distanz zur nächsten Kurve
            self._dst_curve_end = 0.0

        # Wir wollen immer ob in Kurve oder nicht die Distanz zum nächsten Kurvenanfang erhalten
            # ist das nächste Teil außerhalb von den Teilen in der Liste LAYOUT soll wieder auf die erste position geschaut werden
        d, j = rest, (idx + 1) % len(self.LAYOUT)

        # Solange das nächste Teil keine Kurve ist wollen wir die längen auf den aktuellen Rest aufaddieren
        while not self.is_curve[j]:               
            d += self.seg_len[j]
            j = (j + 1) % len(self.LAYOUT)        
        self._dst_next_curve = d

    def step(self, action):
        terminated = False
        truncated = False
        #Aktion umrechnen wie ich mich bewegen muss 
        throttle = (float(action[0]) + 1 ) / 2 * 100

        # Parameter für PT1-Glied auswählen
        K,T = self.throttle_consts[int(round(throttle))] # Listenindex muss ein Integer sein (0..100)
        faktor = np.exp(-self.dt /T)
        v_alt = self._speed
        v_ziel = K

        self._speed = v_ziel + (v_alt-v_ziel) * faktor
        strecke = v_ziel * self.dt + (v_alt - v_ziel) * T * (1 - faktor)

        # Laufband: am Streckenende wieder bei 0 anfangen
        self._pos = (self._pos + strecke) % self.track_len

        self._update_distances()
        self.step_count += 1

        # Crash prüfen
        if self._dst_curve_end != 0.0:
            if self._speed >= self.v_crash:
                terminated = True

        # Truncated prüfen
        # 400 Schritte * 0.05 s = 20 s Episode, das sind bei ca. 2 m/s etwa 10 Runden (Strecke ca. 4.25 m)
        if self.step_count >= 400:
            truncated = True

        # Reward: normierte Geschwindigkeit -> pro Schritt zwischen 0 und 1
        reward = self._speed / self.v_max

        if terminated:
            reward += -50 # entspricht ca. 50-100 Schritten Fahrt; zusätzlich entgehen die restlichen Rewards der Episode
        
        return self._get_obs(), reward, terminated, truncated, {}



