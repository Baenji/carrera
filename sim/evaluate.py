import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from environment import CarreraEnv

# Welches Modell? Entweder als Argument angeben (python evaluate.py models/ppo_...zip),
# sonst wird automatisch das neueste aus models/ genommen
if len(sys.argv) > 1:
    pfad = Path(sys.argv[1])
else:
    pfad = max(Path("models").glob("*.zip"), key=lambda p: p.stat().st_mtime)
print(f"Lade Modell: {pfad}")

env = CarreraEnv()
model = PPO.load(pfad)

# Eine Episode fahren und alles mitschreiben
obs, _ = env.reset(seed=0)
pos, speed, throttle, done = [], [], [], False
while not done:
    action, _ = model.predict(obs, deterministic=True)
    obs, r, term, trunc, _ = env.step(action)
    pos.append(env._pos)
    speed.append(env._speed)
    throttle.append((float(action[0]) + 1) / 2 * 100)
    done = term or trunc
t = np.arange(len(speed)) * env.dt

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 9))

# 1) Geschwindigkeit über Streckenposition, Kurven orange hinterlegt
for s, e, kurve in zip(env.seg_start, env.seg_end, env.is_curve):
    if kurve:
        ax1.axvspan(s, e, color="orange", alpha=0.2)
punkte = ax1.scatter(pos, speed, c=t, cmap="viridis", s=8)   # Farbe = Zeit (spätere Runden heller)
fig.colorbar(punkte, ax=ax1, label="Zeit [s]")
ax1.axhline(env.v_crash, color="red", ls="--", label="v_crash")
ax1.set(xlabel="Position [mm]", ylabel="Geschwindigkeit [mm/s]", title="Speed über Strecke (orange = Kurve)")
ax1.legend()

# 2) Geschwindigkeit über Zeit
ax2.plot(t, speed)
ax2.axhline(env.v_crash, color="red", ls="--")
ax2.set(xlabel="Zeit [s]", ylabel="Geschwindigkeit [mm/s]")

# 3) Gewählter Throttle über Zeit
ax3.plot(t, throttle, color="green")
ax3.set(xlabel="Zeit [s]", ylabel="Throttle [%]", ylim=(0, 100))

fig.suptitle(f"{pfad.stem}: " + ("CRASH" if term else "Episode ohne Crash"))
plt.tight_layout()
plt.show()
