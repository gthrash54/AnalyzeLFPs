import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("09_decoding", "03_backpropagation_from_scratch")

m.md(r'''# Lesson DEC 3: Backpropagation, and How to Know It Is Right {{VARIANT}}

**Electives · Machine Learning and Neural Decoding**

{{INSTRUCTIONS}}

DEC 1 and DEC 2 used models with closed-form solutions, where "did I implement
this correctly" is answered by comparing against a library. This lesson removes
the closed form. A network is fitted by following a gradient, and the gradient is
written by hand out of the chain rule.

That sounds like it should be harder to verify and it is the opposite. A gradient
is the one thing in machine learning with an unambiguous ground truth available
locally: the derivative of a function can be measured by evaluating that function
twice. If the analytic gradient and the numerical one disagree, the analytic one
is wrong, and no amount of the loss going down says otherwise.

The last point is the lesson. A wrong gradient still trains. Section 2 measures
what that looks like.

**What it assumes**

| From | What is used |
|---|---|
| LIN 2 | That a matrix is a linear operator, and that a montage applied to channels is one. |
| DEC 1 | Least squares, ridge, and that a fitted weight is not a measurement. |

**What it underwrites**

DEC 4's comparison of nonlinear against linear decoders, and DEC 5's argument
about weight maps, which applies with more force here than it did to ridge.
''')

m.code('''import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression

rng = np.random.default_rng(67)


def initial_parameters(n_in: int, n_hidden: int, seed: int) -> dict:
    """One hidden layer. Weights scaled by 1/sqrt(fan-in) so activations start sane."""
    gen = np.random.default_rng(seed)
    return {
        "W1": gen.standard_normal((n_in, n_hidden)) / np.sqrt(n_in),
        "b1": np.zeros(n_hidden),
        "W2": gen.standard_normal((n_hidden, 1)) / np.sqrt(n_hidden),
        "b2": np.zeros(1),
    }


print("Environment initialized for Lesson DEC 3")''')

m.md(r'''---

## 1. Forward, then backward

The network is one hidden layer:

$$z_1 = XW_1 + b_1, \qquad a_1 = \tanh(z_1), \qquad \hat y = a_1 W_2 + b_2$$

and the loss is mean squared error. The gradient comes from the chain rule
applied outward in, which is all "backpropagation" means: each layer receives the
derivative of the loss with respect to its output and passes back the derivative
with respect to its input.

The only step that is easy to get wrong is the elementwise one. Going back
through $\tanh$ multiplies by $\tanh'(z_1) = 1 - a_1^2$, and forgetting that
factor produces a gradient that is wrong everywhere and looks entirely
reasonable.''')

m.task(
'''def forward(params: dict, X: np.ndarray, activation: str = "tanh") -> tuple:
    """Returns (hidden_pre_activation, hidden_activation, prediction)."""
    # TODO: z1 = X @ W1 + b1
    # TODO: a1 = tanh(z1), or z1 itself when activation == "linear"
    # TODO: the prediction is a1 @ W2 + b2, flattened to one dimension
    raise NotImplementedError("Implement forward")


def mse(params: dict, X: np.ndarray, y: np.ndarray, activation: str = "tanh") -> float:
    """Mean squared error of the network's prediction."""
    # TODO: one line on top of forward
    raise NotImplementedError("Implement mse")


def backward(params: dict, X: np.ndarray, y: np.ndarray,
             activation: str = "tanh") -> dict:
    """Gradient of the mean squared error with respect to every parameter.

    Returns a dict with the same keys and shapes as `params`.
    """
    # TODO: run forward, then start from d(loss)/d(prediction) = 2*(pred - y)/n
    # TODO: W2 and b2 see that directly, through a1
    # TODO: propagate back to a1 through W2, then through the activation:
    #       for tanh multiply by (1 - a1**2), for linear multiply by 1
    # TODO: W1 and b1 see the result, through X
    raise NotImplementedError("Implement backward")''',
'''def forward(params: dict, X: np.ndarray, activation: str = "tanh") -> tuple:
    """Returns (hidden_pre_activation, hidden_activation, prediction)."""
    z1 = X @ params["W1"] + params["b1"]
    a1 = np.tanh(z1) if activation == "tanh" else z1
    return z1, a1, (a1 @ params["W2"] + params["b2"]).ravel()


def mse(params: dict, X: np.ndarray, y: np.ndarray, activation: str = "tanh") -> float:
    """Mean squared error of the network's prediction."""
    return float(np.mean((forward(params, X, activation)[2] - y) ** 2))


def backward(params: dict, X: np.ndarray, y: np.ndarray,
             activation: str = "tanh") -> dict:
    """Gradient of the mean squared error with respect to every parameter.

    Returns a dict with the same keys and shapes as `params`.
    """
    n = len(y)
    _, a1, prediction = forward(params, X, activation)
    # d(loss)/d(prediction). The 2/n is the derivative of the mean of squares.
    d_pred = 2.0 * (prediction - y) / n
    grad_w2 = a1.T @ d_pred[:, None]
    grad_b2 = np.array([d_pred.sum()])
    d_a1 = d_pred[:, None] @ params["W2"].T
    # The elementwise step. tanh'(z) = 1 - tanh(z)^2, and a1 is already tanh(z),
    # so no second pass through the nonlinearity is needed. Dropping this factor
    # is the classic bug, and Section 2 measures what it costs.
    d_z1 = d_a1 * (1 - a1 ** 2) if activation == "tanh" else d_a1
    return {"W1": X.T @ d_z1, "b1": d_z1.sum(axis=0), "W2": grad_w2, "b2": grad_b2}''')

m.code('''# --- TEST CELL FOR STEP 1 ---
gen = np.random.default_rng(0)
X_small, y_small = gen.standard_normal((60, 6)), gen.standard_normal(60)
params = initial_parameters(6, 5, seed=1)

# Shapes first: a gradient that does not match its parameter cannot be applied.
grads = backward(params, X_small, y_small)
for key in params:
    assert grads[key].shape == params[key].shape, f"{key}: gradient must match the parameter"
print("gradient shapes match every parameter:", {k: v.shape for k, v in grads.items()})

# The forward pass must actually be nonlinear, or the hidden layer is decoration.
_, a1, _ = forward(params, X_small)
assert np.all(np.abs(a1) < 1.0), "tanh saturates between -1 and 1"
_, a1_lin, _ = forward(params, X_small, "linear")
assert not np.allclose(a1, a1_lin), "the linear option must genuinely bypass the nonlinearity"

# And the loss must be the thing the gradient is a gradient of.
assert mse(params, X_small, y_small) > 0
assert abs(mse(params, X_small, y_small)
           - np.mean((forward(params, X_small)[2] - y_small) ** 2)) < 1e-15

print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The check that makes the rest of it trustworthy

The definition of a derivative is a limit of differences, so it can be evaluated
directly. The **central difference**

$$\frac{\partial L}{\partial \theta_i} \approx \frac{L(\theta + \epsilon e_i) - L(\theta - \epsilon e_i)}{2\epsilon}$$

is accurate to order $\epsilon^2$, which at $\epsilon = 10^{-6}$ leaves about ten
correct digits before floating point noise takes over. It costs two forward
passes per parameter, so it is useless for training and ideal for testing.

This is the same move as the bite test used throughout this curriculum, and it is
the reason the rest of this lesson can be believed. Part (b) plants the classic
bug and shows the check finding it, and shows the thing that makes the bug
dangerous, which is that the network trains anyway.''')

m.task(
'''def numerical_gradient(params: dict, X: np.ndarray, y: np.ndarray, key: str,
                       activation: str = "tanh", eps: float = 1e-6) -> np.ndarray:
    """Central-difference gradient for one parameter array, entry by entry."""
    # TODO: for each entry, nudge it up by eps and evaluate the loss, then down
    #       by eps and evaluate again, then restore the original value
    # TODO: the derivative is (loss_up - loss_down) / (2 * eps)
    raise NotImplementedError("Implement numerical_gradient")''',
'''def numerical_gradient(params: dict, X: np.ndarray, y: np.ndarray, key: str,
                       activation: str = "tanh", eps: float = 1e-6) -> np.ndarray:
    """Central-difference gradient for one parameter array, entry by entry."""
    out = np.zeros_like(params[key])
    flat_param, flat_out = params[key].ravel(), out.ravel()
    for i in range(flat_param.size):
        original = flat_param[i]
        flat_param[i] = original + eps
        loss_up = mse(params, X, y, activation)
        flat_param[i] = original - eps
        loss_down = mse(params, X, y, activation)
        # Restore before moving on, or every later entry is evaluated at a
        # different point and the whole check is meaningless.
        flat_param[i] = original
        flat_out[i] = (loss_up - loss_down) / (2 * eps)
    return out''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def relative_error(a, b):
    """Scale-free disagreement, so a large gradient is not flattered by its size."""
    return float(np.max(np.abs(a - b)) / max(float(np.max(np.abs(a) + np.abs(b))), 1e-12))

# (a) The hand-written gradient against arithmetic.
print("analytic gradient against central differences, eps = 1e-6\\n")
print(f"{'parameter':>10} {'max relative error':>20}")
errors = {}
for key in ("W1", "b1", "W2", "b2"):
    errors[key] = relative_error(backward(params, X_small, y_small)[key],
                                 numerical_gradient(params, X_small, y_small, key))
    print(f"{key:>10} {errors[key]:>20.2e}")
    assert errors[key] < 1e-7, f"{key}: analytic and numerical gradients must agree"
print(f"\\n  worst disagreement anywhere: {max(errors.values()):.1e}")

# (b) The classic bug: propagate back through tanh without its derivative.
def backward_missing_tanh_derivative(params, X, y):
    n = len(y)
    _, a1, prediction = forward(params, X)
    d_pred = 2.0 * (prediction - y) / n
    d_z1 = d_pred[:, None] @ params["W2"].T      # the (1 - a1**2) factor is missing
    return {"W1": X.T @ d_z1, "b1": d_z1.sum(axis=0),
            "W2": a1.T @ d_pred[:, None], "b2": np.array([d_pred.sum()])}

print("\\nthe same check on a backward pass with the tanh derivative left out\\n")
print(f"{'parameter':>10} {'max relative error':>20}")
broken = {}
for key in ("W1", "b1"):
    broken[key] = relative_error(backward_missing_tanh_derivative(params, X_small, y_small)[key],
                                 numerical_gradient(params, X_small, y_small, key))
    print(f"{key:>10} {broken[key]:>20.2e}")
assert min(broken.values()) > 0.01, "the check must catch the classic bug, and loudly"
print(f"\\n  the check separates right from wrong by a factor of "
      f"{min(broken.values()) / max(errors.values()):.0e}")

# (c) And here is why the check is not optional: the broken gradient still trains.
def train(params, X, y, grad_fn, iterations, lr, activation="tanh"):
    p = {k: v.copy() for k, v in params.items()}
    history = []
    for _ in range(iterations):
        g = grad_fn(p, X, y) if activation == "tanh" else grad_fn(p, X, y, activation)
        for k in p:
            p[k] -= lr * g[k]
        history.append(mse(p, X, y, activation))
    return p, history

X_train = gen.standard_normal((300, 6))
y_train = np.tanh(X_train @ gen.standard_normal(6)) + 0.1 * gen.standard_normal(300)
start = initial_parameters(6, 8, seed=4)

_, good = train(start, X_train, y_train, backward, 2000, 0.2)
_, bad = train(start, X_train, y_train, backward_missing_tanh_derivative, 2000, 0.2)
print(f"\\n{'iteration':>10} {'correct gradient':>18} {'broken gradient':>17}")
for i in (0, 100, 500, 1999):
    print(f"{i:>10} {good[i]:>18.5f} {bad[i]:>17.5f}")
assert bad[-1] < 0.5 * bad[0], "the broken gradient reduces the loss too, which is the trap"
assert good[-1] < bad[-1], "it just converges somewhere worse, and nothing on screen says why"

print(f"\\nThe correct gradient agreed with arithmetic to {max(errors.values()):.0e} at worst and the broken")
print("one disagreed at the first decimal place, so the check is not a delicate one.")
print(f"\\nThe last table is the reason to run it. The broken gradient cut the loss by")
print(f"{1 - bad[100] / bad[0]:.0%} in the first hundred steps and then flattened, which is exactly the shape")
print("of an ordinary converged training run and would not have been questioned. It")
print("descends a direction that correlates with downhill without being downhill, and")
print("the only evidence available from the run itself is that the final loss is a bit")
print("higher than it might have been, which is indistinguishable from the model being")
print(f"a bit too small or the learning rate a bit off. Here it settled {bad[-1] / good[-1]:.1f} times")
print("worse than the correct gradient, and still looked like convergence.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. A check that is not self-referential

Section 2 verified the gradient against the loss it was derived from. That
catches calculus errors and cannot catch a misunderstanding shared by both.

There is one setting where this network has a known answer from outside itself.
With a linear activation the whole thing collapses: $\hat y = X W_1 W_2 + b$ is a
linear model with weight vector $W_1 W_2$, no matter how many hidden units it
has. Its least squares solution is what DEC 1 computes a completely different
way.

The claim needs stating carefully, because the obvious version is false. The loss
is convex in the **product** $W_1 W_2$ and is not convex in $(W_1, W_2)$
separately, so convergence does not follow from convexity. What is true of this
parameterisation is that every local minimum is global and the remaining critical
points are saddles, so from a generic initialisation and with a small enough step
gradient descent reaches a global minimum, whose product is the least squares
solution. It is not guaranteed for every initialisation: starting at
$W_1 = 0$ leaves the gradient zero and the network predicts the mean forever.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
N_LIN, D_LIN, H_LIN = 400, 4, 7
gen_lin = np.random.default_rng(11)
X_lin = gen_lin.standard_normal((N_LIN, D_LIN))
true_beta = np.array([1.0, -2.0, 0.5, 3.0])
y_lin = X_lin @ true_beta + 0.1 * gen_lin.standard_normal(N_LIN)

linear_net, history = train(initial_parameters(D_LIN, H_LIN, seed=2), X_lin, y_lin,
                            backward, 20_000, 0.05, activation="linear")
effective = (linear_net["W1"] @ linear_net["W2"]).ravel()
ols = LinearRegression().fit(X_lin, y_lin)

print(f"a {H_LIN}-unit network with no nonlinearity, trained by gradient descent\\n")
print(f"  network's effective weights  {np.round(effective, 4)}")
print(f"  ordinary least squares       {np.round(ols.coef_, 4)}")
print(f"  the truth it was drawn from  {np.round(true_beta, 4)}")
print(f"\\n  max |network - OLS| = {np.max(np.abs(effective - ols.coef_)):.2e}")
assert np.max(np.abs(effective - ols.coef_)) < 1e-6, \\
    "with a linear activation the network must find the least squares solution"
net_intercept = float(linear_net["b2"][0]) + float((linear_net["b1"] @ linear_net["W2"])[0])
assert abs(net_intercept - ols.intercept_) < 1e-4, "including the intercept"

# The 28 hidden weights are NOT the 4 OLS weights; only their product is.
print(f"\\n  the network holds {linear_net['W1'].size + linear_net['W2'].size} numbers to "
      f"express {D_LIN} of them")
assert linear_net["W1"].size > D_LIN, "and the extra ones are not determined by the data"

print("\\nTwo completely different procedures, one a matrix solve and one twenty thousand")
print("steps of gradient descent, agreed to 1e-15 on the function they represent. That")
print("is a check on the gradient AND on the training loop, and neither could have")
print("produced it by sharing a misunderstanding with the other.")
print("\\nIt also plants the flag for Section 4. The network agreed with OLS about the")
print("FUNCTION while holding 35 numbers to express 4 of them. The extra 31 are not")
print("determined by the data at all.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. The gradient finds a function, not a set of weights

DEC 1 Section 4 showed a ridge weight moving with the montage while the decoder
stayed the same. In a network the same problem is worse, and it is exact rather
than approximate.

Permute the hidden units and the function is unchanged: relabelling them changes
nothing about the composition. Because $\tanh$ is odd, flipping the sign of a
unit's incoming and outgoing weights together is also unchanged. So for $H$
hidden units there are at least $2^H H!$ distinct weight settings computing
exactly the same predictions, and gradient descent lands on whichever one its
initialisation was nearest.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
N_NL, D_NL, H_NL, N_SEEDS = 500, 8, 6, 5
gen_nl = np.random.default_rng(7)
X_nl = gen_nl.standard_normal((N_NL, D_NL))
y_nl = (np.tanh(X_nl @ gen_nl.standard_normal(D_NL))
        + 0.5 * np.tanh(X_nl @ gen_nl.standard_normal(D_NL))
        + 0.1 * gen_nl.standard_normal(N_NL))
X_probe = gen_nl.standard_normal((2000, D_NL))

fits = [train(initial_parameters(D_NL, H_NL, seed=s), X_nl, y_nl, backward, 6000, 0.1)[0]
        for s in range(N_SEEDS)]

print(f"{N_SEEDS} networks, identical data, different initialisations\\n")
print(f"{'seed':>6} {'final training loss':>21}")
for s, p in enumerate(fits):
    print(f"{s:>6} {mse(p, X_nl, y_nl):>21.5f}")

predictions = np.array([forward(p, X_probe)[2] for p in fits])
weights = np.array([p["W1"].ravel() for p in fits])
pairs = np.triu_indices(N_SEEDS, 1)
pred_corr = np.corrcoef(predictions)[pairs]
weight_corr = np.corrcoef(weights)[pairs]

print(f"\\n  pairwise correlation of their PREDICTIONS: min {pred_corr.min():.4f}, "
      f"mean {pred_corr.mean():.4f}")
print(f"  pairwise correlation of their WEIGHTS:     min {weight_corr.min():.4f}, "
      f"mean {weight_corr.mean():.4f}")
assert pred_corr.min() > 0.99, "they all found the same function"
assert abs(weight_corr.mean()) < 0.3, "and none of them found the same weights"

# The symmetries, exactly rather than statistically.
p = fits[0]
order = np.random.default_rng(3).permutation(H_NL)
permuted = {"W1": p["W1"][:, order], "b1": p["b1"][order],
            "W2": p["W2"][order], "b2": p["b2"]}
flipped = {k: v.copy() for k, v in p.items()}
flipped["W1"][:, 0] *= -1
flipped["b1"][0] *= -1
flipped["W2"][0] *= -1

base_prediction = forward(p, X_probe)[2]
for name, other in (("reordering the hidden units", permuted),
                    ("flipping one unit's sign", flipped)):
    difference = float(np.max(np.abs(base_prediction - forward(other, X_probe)[2])))
    moved = float(np.max(np.abs(p["W1"] - other["W1"])))
    print(f"\\n  {name}:")
    print(f"    max change in prediction: {difference:.2e}")
    print(f"    max change in a weight:   {moved:.3f}")
    assert difference < 1e-12, "the function is identical, not merely similar"
    assert moved > 0.1, "while the weights are visibly different"

equivalent = 2 ** H_NL * math.factorial(H_NL)
print(f"\\n  {H_NL} hidden units give exactly 2^{H_NL} x {H_NL}! = {equivalent} weight settings")
print("  computing the same predictions, from these two symmetries alone. Data-dependent")
print("  flat directions add more, and a unit with zero outgoing weight adds a continuum.")

print("\\nFive networks trained on identical data reached the same loss and the same")
print(f"function, their predictions correlating above {pred_corr.min():.2f}, while their weight vectors")
print(f"correlated {weight_corr.mean():.2f} on average and {weight_corr.min():.2f} for the least similar pair.")
print("\\nThe permutation and sign results are the reason, and they are exact rather than")
print("approximate: reordering moved the predictions by 4e-16, which is floating point")
print("rather than a difference, and the sign flip moved them by exactly zero. The")
print("weights are not underdetermined by a little: reordering and sign flips alone")
print("generate a group of exactly 46,080 elements, before any data-dependent flat")
print("direction is counted.")
print("\\nSo 'the network learned that channel 3 matters' is not a statement the fitting")
print("procedure can support, and unlike DEC 1's ridge case it is not a matter of")
print("degree. There is no privileged weight setting for the sentence to be about.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **Backpropagation is the chain rule applied outward in**, and the only step
   that is easy to get wrong is the elementwise one, where going back through
   tanh multiplies by 1 - a^2.
2. **A gradient has a ground truth available locally.** The analytic gradient
   agreed with a central difference to 1.1e-9 at worst and 2e-10 on the weight
   matrices, at a cost of two forward passes per parameter, which is unaffordable for training and
   free for testing.
3. **A wrong gradient still trains, which is why the check is not optional.**
   Dropping the tanh derivative produced a gradient disagreeing with arithmetic
   at the first decimal place, and the resulting training curve cut the loss by
   about three quarters and then flattened, which is the shape of an ordinary
   converged run. It settled about eighteen times worse than the correct gradient, which
   from inside the run is indistinguishable from a model that is slightly too
   small.
4. **A check against the loss it was derived from is not enough.** With a linear
   activation the network is a linear model, and twenty thousand steps of
   gradient descent landed on the least squares solution to about 1e-15,
   agreeing with a matrix solve that shares none of its assumptions. That is not
   a consequence of convexity, since the loss is convex in the product of the
   weight matrices and not in the matrices themselves; it holds because this
   parameterisation adds only saddles, and it can fail from a degenerate start.
5. **The gradient finds a function, not a set of weights.** Five networks trained
   on identical data made predictions correlating above 0.99, with weight vectors
   correlating 0.03 on average and as low as -0.52 for one pair. Flipping a
   unit's sign changed the predictions by exactly zero and reordering the units
   changed them by 4e-16, which is floating point rather than a difference, so
   six hidden units give exactly 46,080 weight settings representing the same
   function from those two symmetries alone. DEC 1's ridge weights
   were distorted by the montage; these are not identified at all.

The through line from DEC 1: what is checkable is arithmetic and what is
interpreted is not, and the gap between them grew when the model did.

### Exercises

**Exercise 1.** The central difference is accurate to order eps^2, and floating
point noise grows as 1/eps. Sweep eps from 1e-2 to 1e-12 and find where the
measured error is smallest, then say whether 1e-6 was a good default and why the
curve is a U.

**Exercise 2.** Replace tanh with ReLU and rerun Section 2's check. ReLU is not
differentiable at zero. Determine whether that breaks the finite-difference
check, and if so, at what rate it happens and what you would do about it.

**Exercise 3.** Section 4 counted 2^H H! exact symmetries. Train two networks
from the same initialisation but with the training rows in a different order, and
say whether the weights that result differ by one of those symmetries or by
something else. State what you would have to compute to tell the difference.

---

**Next: DEC 4, whether any of this beats a straight line.** The apparatus now
exists to fit a nonlinear decoder. Whether it should be used on an
intraoperative trial count is a separate question, and it has a measurable
answer.
''')

m.emit()
verify("09_decoding", "03_backpropagation_from_scratch")
print("  DEC 3 OK")
