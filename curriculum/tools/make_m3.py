import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("05_dynamics", "03_kalman_online_decoding")

m.md(r'''# Lesson POP 3: Recursive Online Decoding with the Kalman Filter {{VARIANT}}

**Analysis · Population Dynamics and Latent Structure · final lesson**

{{INSTRUCTIONS}}

POP 1 and POP 2 described activity after the fact, with the whole recording available.
A brain-computer interface, and adaptive stimulation, must estimate the state
**now** from data up to now. That is a different problem, and SIG 2 already showed
why: any filter that looks forward is unavailable, and every causal one is late.

**What it assumes**

| From | What is used |
|---|---|
| LIN 4 | Covariance, and that a poorly conditioned one inverts silently. |
| SIG 2 | That a causal filter has an unavoidable group delay. |
| POP 2 | The observation model $x = \Lambda f + \epsilon$. |

**What it underwrites**

Guardrails's adaptive DBS control loop, which is this filter with a controller
attached.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(91)
print("Environment initialized for Lesson POP 3")''')

m.md(r'''---

## 1. The model, and what recursive buys

A linear-Gaussian state space model is two equations:

$$x_t = A x_{t-1} + w_t, \qquad w_t \sim \mathcal{N}(0, Q)$$
$$y_t = H x_t + v_t, \qquad v_t \sim \mathcal{N}(0, R)$$

The first says how the state evolves, the second how the neural observation
relates to it. $Q$ is how much you distrust the dynamics, $R$ how much you
distrust the measurement.

The Kalman filter alternates two steps. **Predict** pushes the estimate forward
by $A$ and inflates its uncertainty by $Q$. **Update** corrects it toward the new
measurement, by an amount set by the **Kalman gain**

$$K_t = P_t^- H^{\top}\left(H P_t^- H^{\top} + R\right)^{-1}$$

which is a ratio of uncertainties: how much you doubt your prediction against how
much you doubt the measurement. When $R$ is large the gain is small and the
filter trusts its model; when $R$ is small it follows the data.

The word recursive matters. The estimate depends on all past data but stores only
the current state and its covariance, so cost per sample is constant and does not
grow with the length of the recording. That is what makes it usable online.''')

m.task(
'''def kalman_filter(y: np.ndarray, A: np.ndarray, H: np.ndarray,
                  Q: np.ndarray, R: np.ndarray, x0: np.ndarray, P0: np.ndarray):
    """Run a Kalman filter over observations `y` of shape [n_obs, n_steps].

    Returns (states, gains) where `states` is [n_state, n_steps] and `gains` is a
    list of the Kalman gain matrices, so the trade can be inspected.

    Production equivalent: `pykalman`, or `statsmodels.tsa.statespace`.
    """
    # TODO: initialise x = x0, P = P0
    # TODO: for each time step: PREDICT with x = A x, P = A P A.T + Q
    # TODO: then UPDATE: S = H P H.T + R; K = P H.T inv(S)
    # TODO:              x = x + K (y_t - H x); P = (I - K H) P
    # TODO: collect x at each step, and the gains
    raise NotImplementedError("Implement kalman_filter")''',
'''def kalman_filter(y: np.ndarray, A: np.ndarray, H: np.ndarray,
                  Q: np.ndarray, R: np.ndarray, x0: np.ndarray, P0: np.ndarray):
    """Run a Kalman filter over observations `y` of shape [n_obs, n_steps].

    Returns (states, gains) where `states` is [n_state, n_steps] and `gains` is a
    list of the Kalman gain matrices, so the trade can be inspected.

    Production equivalent: `pykalman`, or `statsmodels.tsa.statespace`.
    """
    n_state = A.shape[0]
    n_steps = y.shape[1]
    x = np.array(x0, dtype=float).reshape(n_state)
    P = np.array(P0, dtype=float)
    states = np.zeros((n_state, n_steps))
    gains = []
    eye = np.eye(n_state)
    for t in range(n_steps):
        x = A @ x
        P = A @ P @ A.T + Q
        S = H @ P @ H.T + R
        K = P @ H.T @ np.linalg.inv(S)
        x = x + K @ (y[:, t] - H @ x)
        P = (eye - K @ H) @ P
        states[:, t] = x
        gains.append(K)
    return states, gains''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# A smooth 2-D state (position and velocity), observed through 8 noisy channels.
DT = 0.05
A = np.array([[1.0, DT], [0.0, 0.95]])
n_obs = 8
H = rng.standard_normal((n_obs, 2))
Q = np.diag([1e-4, 5e-3])
R_TRUE = np.eye(n_obs) * 0.5
N = 1500

def simulate(seed):
    gen = np.random.default_rng(seed)
    x = np.zeros((2, N))
    for t in range(1, N):
        x[:, t] = A @ x[:, t - 1] + gen.multivariate_normal(np.zeros(2), Q)
    y = H @ x + gen.multivariate_normal(np.zeros(n_obs), R_TRUE, size=N).T
    return x, y

x_true, y_obs = simulate(1)
x_hat, gains = kalman_filter(y_obs, A, H, Q, R_TRUE, np.zeros(2), np.eye(2))

# The baseline any decoder must beat: least squares on each sample alone,
# which uses the measurement and ignores the dynamics entirely.
x_ls = np.linalg.pinv(H) @ y_obs

def rmse(est, truth, skip=100):
    return float(np.sqrt(np.mean((est[:, skip:] - truth[:, skip:]) ** 2)))

print(f"per-sample least squares RMSE : {rmse(x_ls, x_true):.4f}")
print(f"Kalman filter RMSE            : {rmse(x_hat, x_true):.4f}")
print(f"improvement                   : {100*(1 - rmse(x_hat, x_true)/rmse(x_ls, x_true)):.0f}%")
assert rmse(x_hat, x_true) < 0.6 * rmse(x_ls, x_true), \\
    "using the dynamics must beat ignoring them"

# The gain converges, which is why a steady-state gain is often used instead.
gain_norms = [np.linalg.norm(g) for g in gains]
print(f"\\ngain norm at t=1: {gain_norms[0]:.4f}, t=50: {gain_norms[50]:.4f}, "
      f"t=1400: {gain_norms[1400]:.4f}")
assert abs(gain_norms[1400] - gain_norms[500]) < 0.02 * gain_norms[500], \\
    "the gain must converge to a steady state"
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The gain is a ratio, and it is set by numbers you assert

$Q$ and $R$ are not measured by the filter. They are supplied, and the gain is a
ratio between them, so **the filter's behaviour is determined by a belief you
asserted rather than by the data.**

Getting them wrong does not produce an error. It produces a filter that is
confidently too smooth or confidently too jumpy, and the output looks entirely
reasonable in both cases. Below, the true noise levels are held fixed and only
the filter's assumptions are varied.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
print(f"{'assumed R / true R':>20} {'RMSE':>9} {'gain norm':>11} {'behaviour':>22}")
res = {}
for factor in (0.01, 0.1, 1.0, 10.0, 100.0):
    xh, gs = kalman_filter(y_obs, A, H, Q, R_TRUE * factor, np.zeros(2), np.eye(2))
    res[factor] = (rmse(xh, x_true), float(np.linalg.norm(gs[-1])))
    behaviour = ("trusts data" if factor < 1 else "trusts model" if factor > 1 else "correct")
    print(f"{factor:>20g} {res[factor][0]:>9.4f} {res[factor][1]:>11.4f} {behaviour:>22}")

assert res[1.0][0] == min(r[0] for r in res.values()), \\
    "the correctly specified filter must be the best one"
assert res[0.01][1] > res[100.0][1], \\
    "under-stating measurement noise raises the gain, over-stating lowers it"
assert res[100.0][0] > 1.5 * res[1.0][0], "over-smoothing costs real accuracy"

# And the failure is silent: nothing in the filter's own output flags it. Its
# reported uncertainty is a function of Q, R and H alone, not of the residuals.
xh_bad, gs_bad = kalman_filter(y_obs, A, H, Q, R_TRUE * 100, np.zeros(2), np.eye(2))
resid_good = y_obs - H @ x_hat
resid_bad = y_obs - H @ xh_bad
print(f"\\nresidual variance, correct filter    : {np.var(resid_good):.4f}")
print(f"residual variance, over-smoothed     : {np.var(resid_bad):.4f}")
assert np.var(resid_bad) > np.var(resid_good), \\
    "the residuals DO carry the evidence, even though the covariance does not"
print("\\nThe filter's own uncertainty estimate cannot detect this, because it never")
print("looks at the residuals. The residuals can, which is why an innovation check")
print("belongs in any deployed decoder.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Latency, which SIG 2 already priced

A Kalman filter is causal, so SIG 2's conclusion applies without modification: the
estimate at time $t$ uses no information after $t$, and a state that changes
abruptly is followed with a lag.

The lag is not a bug to be tuned away. It is the same trade as the gain: a filter
that responds instantly to a step is one that also responds instantly to noise.
Below, a step change is introduced and the lag measured against the smoothing
benefit, across the same range of assumed $R$.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
x_step = np.zeros((2, N))
x_step[0, N // 2:] = 1.0                          # an abrupt state change at the midpoint
y_step = H @ x_step + rng.multivariate_normal(np.zeros(n_obs), R_TRUE, size=N).T

def lag_samples(est, onset=N // 2, level=0.63):
    """Samples after onset before the estimate first reaches `level` of the step."""
    after = est[0, onset:]
    idx = np.flatnonzero(after > level)
    return int(idx[0]) if idx.size else N

print(f"{'assumed R / true R':>20} {'lag (samples)':>15} {'noise sd before step':>22}")
lags = {}
for factor in (0.1, 1.0, 10.0, 100.0):
    xh_s, _ = kalman_filter(y_step, A, H, Q, R_TRUE * factor, np.zeros(2), np.eye(2))
    lags[factor] = lag_samples(xh_s)
    pre_noise = float(np.std(xh_s[0, 100:N // 2 - 50]))
    print(f"{factor:>20g} {lags[factor]:>15} {pre_noise:>22.4f}")

assert lags[100.0] > lags[0.1], "a filter that trusts its model is slower to a step"
assert lags[0.1] < 0.5 * lags[100.0], "one that trusts the data follows several times sooner"

xh_fast, _ = kalman_filter(y_step, A, H, Q, R_TRUE * 0.1, np.zeros(2), np.eye(2))
xh_slow, _ = kalman_filter(y_step, A, H, Q, R_TRUE * 100, np.zeros(2), np.eye(2))
noise_fast = float(np.std(xh_fast[0, 100:N // 2 - 50]))
noise_slow = float(np.std(xh_slow[0, 100:N // 2 - 50]))
print(f"\\nfast filter: lag {lags[0.1]:>3} samples, pre-step noise {noise_fast:.4f}")
print(f"slow filter: lag {lags[100.0]:>3} samples, pre-step noise {noise_slow:.4f}")
assert noise_fast > noise_slow, "the fast filter pays for its speed in noise"
print("\\nThat is the same exchange SIG 2 measured for a causal bandpass, in different")
print("coordinates: responsiveness against smoothness, with no setting that avoids it.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established, and what Population Dynamics established

1. A Kalman filter uses the dynamics as well as the measurement and beat
   per-sample least squares by a large margin on the same data. Its gain
   converges to a steady state, which is why deployed decoders often use a fixed
   gain and skip the covariance recursion.
2. The gain is a ratio of $Q$ to $R$, and **both are asserted rather than
   measured**. Misstating $R$ by a factor of 100 costs real accuracy while the
   filter's own reported uncertainty stays silent, because that uncertainty
   depends only on $Q$, $R$ and $H$ and never on the residuals. The residuals do
   carry the evidence, so an innovation check belongs in any deployed decoder.
3. A causal filter is late: 12 samples when it trusts the data against 57 when
   it trusts the model, and the faster one is 2.5 times noisier before the step.
   How late is the same knob as how noisy. This is
   SIG 2's trade in state-space coordinates.

**Population Dynamics is complete.** POP 1 found that reported dimensionality is a statement
about epoch length and smoothing kernel at least as much as about the brain. POP 2
found that factor analysis has its advertised advantage only when given a spare
factor, and that its central assumption is false for an electrode array until a
montage makes it true. POP 3 found that the online decoder's behaviour is set by two
covariances nobody measures.

### Exercises

**Exercise 1.** Estimate $R$ from data rather than asserting it, using the
residuals of a first-pass filter, and iterate. Does it converge to the truth?
This is the idea behind adaptive Kalman filtering.

**Exercise 2.** POP 2 showed that one bad channel captures PCA. Add a bad channel
here, with 40 times the variance of the others, and see what it does to the
decoder. Then repair it by adjusting $R$ rather than by removing the channel.

**Exercise 3.** Adaptive DBS updates stimulation every 100 ms. Given Section 3's
lag figures, choose an assumed $R$ for a beta-power decoder and state, in
milliseconds, the delay your choice imposes between a physiological change and
the stimulator responding to it.
''')

m.emit()
verify("05_dynamics", "03_kalman_online_decoding")
print("  POP 3 OK")
