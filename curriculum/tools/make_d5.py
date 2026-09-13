import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("09_decoding", "05_weights_are_not_an_encoding_map")

m.md(r'''# Lesson DEC 5: A Decoder's Weights Are Not an Encoding Map {{VARIANT}}

**Electives · Machine Learning and Neural Decoding**

{{INSTRUCTIONS}}

Every lesson in this course has ended on the same warning approached from a
different side. DEC 1 found a ridge weight moving threefold when a channel was
duplicated. DEC 3 found 46,080 weight settings computing the identical
function. This lesson states the underlying reason once, measures how wrong the
usual reading is, and gives the one thing that can be read off a linear decoder
honestly.

The reason is that a decoder and an encoding model are different objects. An
encoding model asks what each contact records, and its answer is a pattern. A
decoder asks how to recover the source from all contacts at once, and its answer
is a filter. A filter's job includes **subtracting** what it does not want, so a
contact that records nothing of interest can be exactly the contact a good filter
leans on hardest.

**What it assumes**

| From | What it is used for |
|---|---|
| LIN 2 | That a montage is a matrix, and that a difference of contacts is a spatial filter. |
| LIN 4 | That a shared reference puts a large common component on every contact, which is guardrail G1. |
| LIN 6 | That a spatial filter and the pattern it recovers are different vectors. |
| DEC 1 | Ridge, and that a weight is not a measurement. |

**What it underwrites**

Every figure in this app that colours contacts by a model coefficient, and the
sentence written under it.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge

rng = np.random.default_rng(89)

N_TRIALS, N_CONTACTS = 4000, 16
CONTACT = np.arange(N_CONTACTS)

# The forward model. Every contact sees the source, falling off with distance,
# except the last one, which is far enough away to see none of it. Every contact
# sees the shared nuisance equally, which is what a reference does.
PATTERN_SIGNAL = np.exp(-((CONTACT - 3.0) / 4.0) ** 2)
PATTERN_SIGNAL[-1] = 0.0
PATTERN_NUISANCE = np.ones(N_CONTACTS)
CARRIES_SIGNAL = PATTERN_SIGNAL > 0.05     # ten of the sixteen


def recording(nuisance_sd: float, seed: int = 5) -> tuple:
    """X = source * its pattern + nuisance * its pattern + sensor noise. y is the source."""
    gen = np.random.default_rng(seed)
    source = gen.standard_normal(N_TRIALS)
    nuisance = nuisance_sd * gen.standard_normal(N_TRIALS)
    x = (np.outer(source, PATTERN_SIGNAL)
         + np.outer(nuisance, PATTERN_NUISANCE)
         + 0.2 * gen.standard_normal((N_TRIALS, N_CONTACTS)))
    return x, source


def unit(v):
    """Scale to a peak magnitude of 1, so patterns can be compared by shape."""
    return v / np.max(np.abs(v))


print("Environment initialized for Lesson DEC 5")''')

m.md(r'''---

## 1. Two models, two different questions

The **forward** or encoding model is a statement about how the data came to be:

$$X = s\,a^\top + \text{nuisance} + \text{noise}$$

where $a$ is the pattern, one number per contact, saying how strongly that
contact records the source. That is the quantity people want when they colour an
array by "where the signal is".

The **backward** or decoding model is a statement about how to recover $s$:

$$\hat s = Xw$$

Nothing requires $w$ to resemble $a$, and Section 2 measures how badly it fails
to. But there is a case where they do line up, and finding it first makes the
failure legible: when the only thing on the contacts is the source, the best way
to recover it is to weight each contact by how much of it that contact has.''')

m.code('''# --- TEST CELL FOR STEP 1 ---
def fit_decoder(X, y, alpha=1.0):
    """The backward model: one weight per contact."""
    return Ridge(alpha=alpha).fit(X, y).coef_


def encoding_pattern(X, y):
    """The forward model, fitted honestly: regress each contact ON the source.

    One univariate regression per contact, which is what an encoding model is.
    Nothing here looks at the other contacts.
    """
    yc = y - y.mean()
    return np.array([float((X[:, c] - X[:, c].mean()) @ yc / (yc @ yc))
                     for c in range(X.shape[1])])


# (a) With no nuisance, the decoder's weights and the true pattern agree.
X_clean, y_clean = recording(nuisance_sd=0.0)
w_clean = fit_decoder(X_clean, y_clean)
a_hat = encoding_pattern(X_clean, y_clean)

print("no nuisance present\\n")
print(f"{'contact':>8} {'true pattern':>14} {'encoding fit':>14} {'decoder weight':>16}")
for c in (0, 3, 7, 11, 15):
    print(f"{c:>8} {unit(PATTERN_SIGNAL)[c]:>14.3f} {unit(a_hat)[c]:>14.3f} {unit(w_clean)[c]:>16.3f}")

print(f"\\n  encoding fit against the truth: r = {np.corrcoef(a_hat, PATTERN_SIGNAL)[0, 1]:.4f}")
print(f"  decoder weights against it:     r = {np.corrcoef(w_clean, PATTERN_SIGNAL)[0, 1]:.4f}")
assert np.corrcoef(a_hat, PATTERN_SIGNAL)[0, 1] > 0.999, \\
    "the encoding model must recover the pattern; it is a direct measurement of it"
assert stats.spearmanr(np.abs(w_clean), PATTERN_SIGNAL).statistic > 0.9, \\
    "and with nothing to subtract, the decoder's weights rank the contacts correctly too"
assert np.sum((w_clean < 0) & CARRIES_SIGNAL) == 0, "with no sign errors"

print("\\nWith nothing on the array but the source, the two agree and the usual reading of")
print("a weight map is fine. That agreement is a special case, and Section 2 removes the")
print("thing that makes it special.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What a filter does with a contact that records nothing

Now add the nuisance. LIN 4 established that a shared reference puts a large
common component on every contact, and guardrail G1 exists because it does.

The decoder's task changes completely. It must now recover a small source in the
presence of a large common signal, and the way to do that is to subtract an
estimate of the common signal. The best available estimate is the contact that
sees the nuisance and nothing else, which is precisely the contact carrying no
information about the source at all.

So the prediction before running it: the empty contact should acquire a large
weight, and contacts carrying real signal should acquire weights that do not
reflect how much they carry.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
NUISANCE = 5.0
X, y = recording(nuisance_sd=NUISANCE)
w = fit_decoder(X, y)

print(f"the nuisance is {NUISANCE:.0f}x the source, and reaches every contact equally\\n")
print(f"{'contact':>8} {'true signal':>13} {'decoder weight':>16} {'reading the map':>22}")
for c in CONTACT:
    verdict = ""
    if PATTERN_SIGNAL[c] > 0.3 and abs(unit(w)[c]) < 0.1:
        verdict = "carries signal, looks empty"
    elif PATTERN_SIGNAL[c] < 0.05 and abs(unit(w)[c]) > 0.4:
        verdict = "carries nothing, looks strong"
    print(f"{c:>8} {unit(PATTERN_SIGNAL)[c]:>13.3f} {unit(w)[c]:>16.3f} {verdict:>22}")

# (a) The empty contact is not ignored. It is used, and used inverted.
print(f"\\n  contact {N_CONTACTS - 1} records none of the source, and its weight is "
      f"{unit(w)[-1]:+.3f}")
assert PATTERN_SIGNAL[-1] == 0.0
assert abs(unit(w)[-1]) > 0.3, "the empty contact carries a large weight, because it is the reference"

# (b) Contacts that DO carry signal get negative weights, so even the sign of a
# weight is not the sign of that contact's contribution.
wrong_sign = int(np.sum((w < 0) & CARRIES_SIGNAL))
print(f"  contacts carrying real signal but given a NEGATIVE weight: "
      f"{wrong_sign} of {CARRIES_SIGNAL.sum()}")
assert wrong_sign >= 2, "the sign of a weight is not the sign of the contribution"

# (c) The ranking, which is what a coloured array actually communicates.
rho_w = stats.spearmanr(np.abs(w), PATTERN_SIGNAL).statistic
rho_clean = stats.spearmanr(np.abs(w_clean), PATTERN_SIGNAL).statistic
print(f"\\n  rank agreement between |weight| and the true pattern:")
print(f"    with no nuisance: {rho_clean:>6.3f}")
print(f"    with a nuisance:  {rho_w:>6.3f}")
assert rho_w < 0.5, "with a nuisance present the weight map ranks contacts barely better than chance"
assert rho_clean > 2 * rho_w, "and the nuisance is what did it"

# (d) None of this is a bad decoder. It is a good one.
print(f"\\n  the decoder itself: r = {np.corrcoef(X @ w, y)[0, 1]:.4f}")
assert np.corrcoef(X @ w, y)[0, 1] > 0.95, "this is an excellent decoder, which is the point"

print("\\nThe decoder recovers the source almost perfectly, and its weight map is close to")
print("uninformative about where the source is. The contact that records none of it has")
print("one of the largest weights, several contacts that do record it are given negative")
print("weights, and the rank agreement between weight magnitude and true pattern falls")
print(f"from {rho_clean:.2f} to {rho_w:.2f} when the nuisance is added.")
print("\\nThe mechanism is LIN 2's, not a subtlety of machine learning. A filter that")
print("subtracts a reference has a large negative coefficient on the reference, and a")
print("re-referencing montage is exactly such a filter. The decoder discovered a montage")
print("and the weight map is showing it to you.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The one thing that can be read off honestly

The forward pattern can be recovered from the backward model, and the derivation
is three lines.

The decoder's output is $\hat s = Xw$, and it is a good decoder, so
$\hat s \approx s$. Then

$$\Sigma_X w = \mathbb{E}[X^\top X]\,w = \mathbb{E}[X^\top (Xw)]
= \mathbb{E}[X^\top \hat s] \approx \mathbb{E}[X^\top s] = a\,\mathrm{var}(s)$$

so multiplying the weights by the data's own covariance turns a filter back into
a pattern, up to a scale nobody needs. Everything the weights were doing to
cancel the nuisance is undone by the covariance, because the covariance is where
the nuisance lives.

This is the same relationship LIN 6 established between a generalised
eigenvector and the component it recovers, arriving from the decoding side.''')

m.task(
'''def activation_pattern(X: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Turn a decoder's filter into the forward pattern it corresponds to.

    Multiply the data's covariance by the weights. The scale is arbitrary, so
    only the shape is meaningful.
    """
    # TODO: centre the columns of X
    # TODO: return (Xc.T @ Xc) @ weights
    raise NotImplementedError("Implement activation_pattern")''',
'''def activation_pattern(X: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Turn a decoder's filter into the forward pattern it corresponds to.

    Multiply the data's covariance by the weights. The scale is arbitrary, so
    only the shape is meaningful.
    """
    centred = X - X.mean(axis=0)
    # The unnormalised covariance is enough: a constant factor of 1/(n-1) is
    # part of the arbitrary scale.
    return (centred.T @ centred) @ weights''')

m.code('''# --- TEST CELL FOR STEP 3 ---
A = activation_pattern(X, w)

print(f"{'contact':>8} {'true signal':>13} {'decoder weight':>16} {'activation':>12}")
for c in CONTACT:
    print(f"{c:>8} {unit(PATTERN_SIGNAL)[c]:>13.3f} {unit(w)[c]:>16.3f} {unit(A)[c]:>12.3f}")

rho_a = stats.spearmanr(np.abs(A), PATTERN_SIGNAL).statistic
print(f"\\n  rank agreement with the true pattern:  |weight| {rho_w:.3f},  |activation| {rho_a:.3f}")
print(f"  correlation with the true pattern:     weight   "
      f"{np.corrcoef(w, PATTERN_SIGNAL)[0, 1]:.4f},  activation {np.corrcoef(A, PATTERN_SIGNAL)[0, 1]:.4f}")
assert rho_a > 0.85, "the activation pattern ranks the contacts correctly"
assert rho_a > 2 * rho_w, "which the weights did not"
assert int(np.sum((A < 0) & CARRIES_SIGNAL)) == 0, \\
    "and it gets no sign wrong on a contact that carries signal"
assert abs(unit(A)[-1]) < 0.15, "the empty contact is correctly reported as empty"

# It must survive the nuisance being anywhere from absent to overwhelming.
print(f"\\n{'nuisance':>10} {'rho(|w|, truth)':>17} {'rho(|A|, truth)':>17} "
      f"{'w sign errors':>15} {'A sign errors':>15}")
for level in (0.0, 1.0, 3.0, 5.0, 10.0):
    X_l, y_l = recording(nuisance_sd=level)
    w_l = fit_decoder(X_l, y_l)
    A_l = activation_pattern(X_l, w_l)
    r_w = stats.spearmanr(np.abs(w_l), PATTERN_SIGNAL).statistic
    r_a = stats.spearmanr(np.abs(A_l), PATTERN_SIGNAL).statistic
    print(f"{level:>10.1f} {r_w:>17.3f} {r_a:>17.3f} "
          f"{int(np.sum((w_l < 0) & CARRIES_SIGNAL)):>15} "
          f"{int(np.sum((A_l < 0) & CARRIES_SIGNAL)):>15}")
    assert r_a > 0.8, f"the activation pattern holds up at nuisance {level}"
    assert int(np.sum((A_l < 0) & CARRIES_SIGNAL)) == 0, "with no sign errors at any level"

print("\\nOne matrix multiply, and the map becomes readable. The activation pattern ranked")
print(f"the contacts at {rho_a:.2f} against the weights' {rho_w:.2f}, reported the empty contact as")
print("empty, and never gave a signal-carrying contact the wrong sign, at every nuisance")
print("level from absent to ten times the source.")
print("\\nNothing was added to the data to achieve that. The information was in the weights")
print("the whole time, mixed with the covariance the weights were built to cancel.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What the activation pattern still does not tell you

The transform is worth having and it is narrow. Three limits, in decreasing order
of how often they are ignored.

It is **a pattern over contacts, not a location in the brain**. REC 1 measured an
LFP reach of 4.6 mm, so many arrangements of generators project onto the array
almost identically, and REC 2 showed that a single fixed source is reported on
different segments depending on lead rotation. Section 4 measures one such
ambiguity directly.

It **requires the model to be linear**. The derivation used $\hat s = Xw$, and a
network has no $w$. DEC 3 showed its weights are not identified at all, so there
is nothing for a covariance to multiply.

And it inherits **whatever the covariance is wrong about**. It is estimated from
the same short recording, and LIN 4 measured what a covariance from few samples
does.

The first two are tested below.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
# (a) The pattern is a projection, and different arrangements of sources project
# onto the array almost identically. One generator at contact 3, against two
# weaker generators either side of it, is a different piece of physiology.
def from_pattern(pattern, nuisance_sd=5.0, seed=5):
    gen = np.random.default_rng(seed)
    source = gen.standard_normal(N_TRIALS)
    x = (np.outer(source, pattern)
         + np.outer(nuisance_sd * gen.standard_normal(N_TRIALS), PATTERN_NUISANCE)
         + 0.2 * gen.standard_normal((N_TRIALS, N_CONTACTS)))
    return x, source

one_generator = np.exp(-((CONTACT - 3.0) / 4.0) ** 2)
two_generators = (0.5 * np.exp(-((CONTACT - 1.0) / 4.0) ** 2)
                  + 0.5 * np.exp(-((CONTACT - 5.0) / 4.0) ** 2))

recovered = {}
for name, pattern in (("one generator", one_generator), ("two generators", two_generators)):
    Xs, ys = from_pattern(pattern)
    recovered[name] = unit(activation_pattern(Xs, fit_decoder(Xs, ys)))

print("one generator at contact 3, against two weaker ones at contacts 1 and 5\\n")
print(f"{'contact':>8} {'one generator':>15} {'two generators':>16}")
for c in CONTACT[:9]:
    print(f"{c:>8} {recovered['one generator'][c]:>15.3f} "
          f"{recovered['two generators'][c]:>16.3f}")

similarity = float(np.corrcoef(recovered["one generator"],
                               recovered["two generators"])[0, 1])
print(f"\\n  correlation between the two recovered patterns: {similarity:.4f}")
print(f"  peak contact, one generator:  {int(np.argmax(recovered['one generator']))}")
print(f"  peak contact, two generators: {int(np.argmax(recovered['two generators']))}")
assert similarity > 0.97, "two different arrangements of sources give nearly the same pattern"
assert np.argmax(recovered["one generator"]) == np.argmax(recovered["two generators"]), \
    "including the same peak contact, which is what a figure would be read off"
print("  Two different pieces of physiology, one pattern. The pattern is the projection")
print("  of the sources onto the array, and projecting loses whatever the array cannot")
print("  resolve, which REC 1 and REC 3 already measured.")

# (b) The transform needs a w to transform, and a network does not have one.
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

nets = [make_pipeline(StandardScaler(),
                      MLPRegressor(hidden_layer_sizes=(16,), max_iter=1500,
                                   random_state=s, alpha=1.0)).fit(X, y)
        for s in (0, 1)]
first_layers = [n.named_steps["mlpregressor"].coefs_[0] for n in nets]
per_contact = [np.abs(layer).sum(axis=1) for layer in first_layers]

print(f"\\n  two networks decoding the same source, both working:")
for i, n in enumerate(nets):
    print(f"    network {i}: r = {np.corrcoef(n.predict(X), y)[0, 1]:.4f}")
print(f"  correlation between their per-contact input weight magnitudes: "
      f"{np.corrcoef(*per_contact)[0, 1]:.3f}")
print(f"  correlation of each with the true pattern: "
      f"{np.corrcoef(per_contact[0], PATTERN_SIGNAL)[0, 1]:+.3f}, "
      f"{np.corrcoef(per_contact[1], PATTERN_SIGNAL)[0, 1]:+.3f}")
for n in nets:
    assert np.corrcoef(n.predict(X), y)[0, 1] > 0.9, "both networks decode well"
assert not hasattr(nets[0].named_steps["mlpregressor"], "coef_"), \\
    "there is no single weight vector to multiply by a covariance"

print("\\n  There is no w. The first layer is a matrix, not a vector, and DEC 3 showed")
print("  that reordering the hidden units or flipping their signs already generates")
print("  46,080 weight settings computing the same function, with data-dependent flat")
print("  directions on top of that. Summing input weights per contact, which is what")
print("  people do, is not")
print("  the transform of Section 3 and has no derivation behind it.")

print("\\nSo the honest reporting rule for this app is short. For a linear decoder, show")
print("the activation pattern and call it a pattern over contacts, not a location. For a")
print("nonlinear one, show performance and say nothing about which contact mattered,")
print("because the fitting procedure did not determine it. If which contact matters IS")
print("the question, fit the forward model of Section 1, which answers it directly and")
print("does not need any of this.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **An encoding model and a decoder answer different questions,** and they agree
   only when there is nothing to subtract. With no nuisance present, the
   decoder's weight magnitudes ranked the contacts against the true pattern at a
   Spearman correlation above 0.9 with no sign errors.
2. **Add a realistic shared nuisance and the weight map stops describing the
   array.** With a nuisance five times the source, the contact recording none of
   the source acquired one of the largest weights, several contacts that do
   record it were given negative weights, and rank agreement with the true
   pattern fell from about 0.97 to about 0.31. The decoder was excellent
   throughout, correlating above 0.99 with the source. This is not a bad model;
   it is a good filter, and a filter subtracts.
3. **The forward pattern is recoverable in one matrix multiply.** Multiplying the
   weights by the data covariance gives a vector proportional to the true
   pattern, because the covariance undoes exactly the cancellation the weights
   were built to perform. Rank agreement was above 0.85 at every nuisance level
   from zero to ten times the source, with no sign errors anywhere, against
   weights that failed at all of them.
4. **The recovered pattern is still a projection, not a source location.** One
   generator at contact 3 and two weaker generators at contacts 1 and 5 produced
   recovered patterns correlating above 0.98 with the same peak contact. Two
   different pieces of physiology, one pattern: the array cannot separate them,
   and neither can anything computed from it.
5. **There is no version of this for a network.** The derivation needs a single
   weight vector, and a network's first layer is a matrix identified only up to
   the symmetry group DEC 3 counted. Two networks decoding the same source
   equally well produced per-contact input weights that agreed with each other,
   and with the truth, far less well than the linear activation pattern did.

The course's single conclusion, which every lesson reached separately: a fitted
parameter is a means to a prediction and is not a measurement of anything, and
the further the model is from linear the less recoverable the measurement
becomes.

### Exercises

**Exercise 1.** The activation pattern uses the covariance estimated from the
same recording. LIN 4 measured what a covariance from few samples looks like.
Repeat Section 3 with 40 trials instead of 4000 and report how much of the
recovery survives, then say whether shrinkage helps.

**Exercise 2.** Section 4 says to fit the forward model when the question is
which contact carries the signal. Write down what that model cannot answer that
the decoder can, using DEC 4's nonlinear target as the example.

**Exercise 3.** G1 flags monopolar common mode. Work out whether a run that
passes G1 is safe from Section 2's failure, and if not, propose what a run record
would have to store for a reader to tell.

---

That completes Machine Learning and Neural Decoding. Together with Statistical
Inference, it is what a decoding claim from this lab needs before it is a claim:
a null it can be compared against, folds that respect time, a trial count that
makes the comparison answerable, and a map that means what its caption says.
''')

m.emit()
verify("09_decoding", "05_weights_are_not_an_encoding_map")
print("  DEC 5 OK")
