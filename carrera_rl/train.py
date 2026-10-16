"""
Training eines RL-Agenten in der Simulation (Stable-Baselines3).

    python -m carrera_rl.train --algo sac --steps 300000 --out models_rl/sac_v1
    tensorboard --logdir models_rl          # Lernkurven ansehen

Danach auswerten:
    python -m carrera_rl.evaluate models_rl/sac_v1/best_model.zip
"""
import argparse
import json
import os

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.callbacks import EvalCallback
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor

from .env import CarreraEnv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--algo", choices=["sac", "ppo"], default="sac")
    ap.add_argument("--steps", type=int, default=300_000, help="Anzahl Regelschritte (30 pro simulierter Sekunde)")
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--vehicle", default="calibration/vehicle.json")
    ap.add_argument("--lane", default="right", choices=["right", "left"])
    ap.add_argument("--u-max", type=float, default=50.0, help="höchstes erlaubtes Gas (%%)")
    ap.add_argument("--no-randomize", action="store_true", help="ohne Zufallsvariation der Fahrzeugparameter")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="models_rl/sac_v1")
    args = ap.parse_args()

    env_kwargs = dict(vehicle=args.vehicle, lane=args.lane, u_max=args.u_max, randomize=not args.no_randomize)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "config.json"), "w") as f:
        json.dump({"args": vars(args), "env_kwargs": env_kwargs}, f, indent=2)

    venv = make_vec_env(CarreraEnv, n_envs=args.n_envs, seed=args.seed, env_kwargs=env_kwargs)
    eval_env = Monitor(CarreraEnv(**{**env_kwargs, "episode_s": 20.0}))
    eval_cb = EvalCallback(eval_env, n_eval_episodes=10, eval_freq=max(10_000 // args.n_envs, 1),
                           best_model_save_path=args.out, log_path=args.out, deterministic=True)

    if args.algo == "sac":
        model = SAC("MlpPolicy", venv, gamma=0.99, learning_rate=3e-4, buffer_size=300_000, batch_size=256,
                    learning_starts=5_000, train_freq=1, gradient_steps=1, verbose=1,
                    tensorboard_log=os.path.dirname(args.out) or ".", seed=args.seed)
    else:
        model = PPO("MlpPolicy", venv, gamma=0.99, n_steps=1024, batch_size=256, learning_rate=3e-4,
                    ent_coef=0.0, verbose=1, tensorboard_log=os.path.dirname(args.out) or ".", seed=args.seed)

    try:
        model.learn(total_timesteps=args.steps, callback=eval_cb, tb_log_name=os.path.basename(args.out))
    except KeyboardInterrupt:
        print("Abgebrochen, speichere aktuellen Stand.")
    model.save(os.path.join(args.out, "final_model"))
    print(f"Gespeichert in {args.out}/ (best_model.zip = bestes Modell in der Zwischenauswertung)")


if __name__ == "__main__":
    main()
