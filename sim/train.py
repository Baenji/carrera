from datetime import datetime
from stable_baselines3 import PPO
from environment import CarreraEnv

name = "ppo_" + datetime.now().strftime("%Y-%m-%d_%H-%M") # eindeutiger Name pro Training, z. B. ppo_2026-11-20_14-30

env = CarreraEnv() # initialisiert eine Simulation (__init__)
model = PPO("MlpPolicy", env, verbose=1, tensorboard_log="./tb_logs/", policy_kwargs=dict(log_std_init=-2)) # PPO bekommt Observation und Action Space vom Carrea env, Verbose gibt Status
model.learn(total_timesteps=2_000_000, tb_log_name=name) # x Anzahl Steps
model.save(f"models/{name}") # wird nie überschrieben, weil jeder Name anders ist
print(f"Modell gespeichert: models/{name}.zip")
