from datetime import datetime
from stable_baselines3 import PPO
from environment import CarreraEnv
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.callbacks import EvalCallback 

if __name__ == "__main__":
    name = "ppo_" + datetime.now().strftime("%Y-%m-%d_%H-%M") # eindeutiger Name pro Training, z. B. ppo_2026-11-20_14-30

    env = make_vec_env(CarreraEnv, n_envs=8, vec_env_cls=DummyVecEnv) # initialisiert eine Simulation (__init__) - startert außerdem 8 instanzen Gleichzeitig (parallel)
    model = PPO("MlpPolicy", env,
                n_steps= 256, # Entsprechend der n_envs mussen die Steps heruntergenommen werden - man muss multipliziert immer auf 2048 kommen also bei 32 envs zum Beispiel 64 steps pro env
                verbose=1, tensorboard_log="./tb_logs/",
                learning_rate=1e-4, # Kleinere Learningrate 
                use_sde = True, # PT1-Glied glättet die Eingabe über ca. 8 Schritte - PPO würfelt das Rauschen in jedem Schritt neu -> gSDE ist für solche trägen Systeme gedacht (Rauschen bleibt über mehrere Schritte gleich)
                sde_sample_freq= 8, 
                policy_kwargs=dict(log_std_init=-2)) # PPO bekommt Observation und Action Space vom Carrea env, Verbose gibt Status

    # EvalCallback sorgt dafür das immer das beste Modell übernommen wird (sonst würden wir nur das letzte nehmen) - So schauen wir alle paar runden ist das aktuelle Modell besser als das zuvor gespeicherte? Wenn ja speichere das  wenn nein altes behalten
    eval_cb = EvalCallback(
        CarreraEnv(),                                  # eigenes Env nur zum Testen
        best_model_save_path=f"models/{name}",         # Ordner, darin liegt best_model.zip
        eval_freq=50_000 // 8,                         # alle 50k Schritte testen (zählt pro Env, daher // n_envs)
        n_eval_episodes=20,                            # über 20 Episoden mitteln
        deterministic=True,                            # ohne Rauschen testen, so wie du später fährst
    )

    model.learn(total_timesteps=1_500_000, tb_log_name=name, callback=eval_cb) # x Anzahl Steps
    model.save(f"models/{name}") # wird nie überschrieben, weil jeder Name anders ist
    print(f"Modell gespeichert: models/{name}.zip")
