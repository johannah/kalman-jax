import numpy as np
import jax.numpy as jnp
from jax.nn import softplus
from utils import softplus_inv
from jax.experimental import optimizers
import matplotlib.pyplot as plt
import time
import pandas as pd
from sde_gp import SDEGP
import priors
import likelihoods
pi = 3.141592653589793

prior = priors.Matern52
lik = likelihoods.Poisson

print('loading coal data ...')
disaster_timings = pd.read_csv('../data/coal.txt', header=None).values[:, 0]

# Discretization
num_time_bins = 200
# Discretize the data
x = np.linspace(min(disaster_timings), max(disaster_timings), num_time_bins).T
y = np.histogram(disaster_timings, np.concatenate([[-1e10], x[:-1] + np.diff(x)/2, [1e10]]))[0][:, None]
# Test points
x_test = x

meanval = np.log(len(disaster_timings)/num_time_bins)  # TODO: incorporate mean

var_f = softplus_inv(0.1)  # GP variance
len_f = softplus_inv(1.0)  # GP lengthscale

theta_prior = jnp.array([var_f, len_f])
theta_lik = jnp.array([])

prior_ = prior(softplus(theta_prior))
lik_ = lik(softplus(theta_lik))

sde_gp_model = SDEGP(prior=prior_, likelihood=lik_, x=x, y=y, x_test=x_test)

opt_init, opt_update, get_params = optimizers.adam(step_size=5e-1)
opt_state = opt_init([theta_prior, theta_lik])  # parameters should be a 2-element list [param_prior, param_likelihood]


def gradient_step(i, state):
    params = get_params(state)
    sde_gp_model.prior.hyp = params[0]
    sde_gp_model.likelihood.hyp = params[1]
    neg_log_marg_lik, gradients = sde_gp_model.neg_log_marg_lik()
    print('iter %2d: var_f=%1.2f len_f=%1.2f, nlml=%2.2f' %
          (i, softplus(params[0][0]), softplus(params[0][1]), neg_log_marg_lik))
    return opt_update(i, gradients, state)


print('optimising the hyperparameters ...')
t0 = time.time()
for j in range(20):
    opt_state = gradient_step(j, opt_state)
t1 = time.time()
print('optimisation time: %2.2f secs' % (t1-t0))

# calculate posterior predictive distribution via filtering and smoothing at train & test locations:
print('calculating the posterior predictive distribution ...')
t0 = time.time()
posterior_mean, posterior_var, _, _ = sde_gp_model.predict()
t1 = time.time()
print('prediction time: %2.2f secs' % (t1-t0))

lb = posterior_mean[:, 0] - 1.96 * posterior_var[:, 0]**0.5
ub = posterior_mean[:, 0] + 1.96 * posterior_var[:, 0]**0.5
x_pred = sde_gp_model.t_all
test_id = sde_gp_model.test_id
link_fn = sde_gp_model.likelihood.link_fn

print('sampling from the posterior ...')
t0 = time.time()
posterior_samp = sde_gp_model.posterior_sample(20)
t1 = time.time()
print('sampling time: %2.2f secs' % (t1-t0))

print('plotting ...')
plt.figure(1, figsize=(12, 5))
plt.clf()
plt.plot(disaster_timings, 0*disaster_timings, 'k+', label='observations', clip_on=False)
plt.plot(x_pred, link_fn(posterior_mean), 'g', label='posterior mean')
plt.fill_between(x_pred, link_fn(lb), link_fn(ub), color='g', alpha=0.05, label='95% confidence')
plt.plot(x_test, link_fn(posterior_samp[test_id, 0, :]), 'g', alpha=0.15)
plt.xlim(x_test[0], x_test[-1])
plt.ylim(0.0)
plt.legend()
plt.title('log-Gaussian Cox process via Kalman smoothing (coal mining disasters)')
plt.xlabel('year')
plt.ylabel('accident intensity')
plt.show()