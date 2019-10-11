__all__ = ['ChaosModel', 'ExponFam', 'VariationalOptimizer', 'SparseVariationalOptimizer']

import numpy as np
import math 
import scipy.stats as st 
import scipy.special as sp
import chaos_basispy as cb


class ChaosModel(object):

	_dim = None

	_order = None

	_basis = None

	_coeffs = None

	def __init__(self, dim, order, coeffs = None, trunc = 'TD', q = None):
		"""
		Initializes the object
		"""
		assert isinstance(dim,int)
		assert isinstance(order,int)
		self._dim = dim
		self._order = order
		self._basis = cb.PolyBasis(self._dim, self._order, 'H', trunc = trunc, q = q)
		#print self._basis._MI_terms.shape[0]
		if coeffs is None:
			self._coeffs = np.zeros(self._basis._MI_terms.shape)
		else:
			assert self._basis._MI_terms.shape[0] == coeffs.shape[0]
			self._coeffs = coeffs

	def eval(self, xi):
		return np.dot(self._basis(xi), self._coeffs)


class ExponFam(object):
	"""
	"""
	_pdf = None

	def __init__(self, pdf):
		"""
		Initializes the object
		"""
		self._pdf = pdf

	def A(self, eta):
		if self._pdf == 'Gauss':
			return - eta[0]**2/(4*eta[1]) - np.log(-2*eta[1]) / 2.
		elif self._pdf == 'Gamma':
			return np.log( sp.gamma(eta[0]+1) ) - (eta[0]+1.) * np.log(-eta[1])
		elif self._pdf == 'Bernoulli':
			return - np.log(sp.expit(eta))
			#if A == np.inf:
			#	return eta
			#else:
			#	return A
		elif self._pdf == 'Beta':
			return np.log(sp.gamma(eta[0])) + np.log(sp.gamma(eta[1])) - np.log(sp.gamma(eta[0]+eta[1]))


	def A_grad(self, eta):
		if self._pdf == 'Gauss':
			return np.array([-eta[0]/(2*eta[1]), eta[0]**2 / (4*eta[1]**2) - 1./(2*eta[1])])
		elif self._pdf == 'Gamma':
			return np.array([sp.digamma(eta[0]+1) - np.log(-eta[1]) , -(eta[0]+1)/eta[1]])
		elif self._pdf == 'Bernoulli':
			return sp.expit(eta)
		elif self._pdf == 'Beta':
			return np.array([sp.digamma(eta[0]) - sp.digamma(eta[0]+eta[1]), sp.digamma(eta[1]) - sp.digamma(eta[0]+eta[1])])

	def map_from_eta(self, eta):
		if self._pdf == 'Gauss':
			return np.array([-eta[0]/(2*eta[1]), -2*eta[1]])
		elif self._pdf == 'Gamma':
			return np.array([eta[0]+1., -eta[1]])
		elif self._pdf == 'Bernoulli':
			return sp.expit(eta)
		elif self._pdf == 'Beta':
			return np.array([eta[0], eta[1]])

	def map_to_eta(self, params):
		if self._pdf == 'Gauss':
			return np.array([params[0]*params[1], -params[1] / 2.])
		elif self._pdf == 'Gamma':
			return np.array([params[0]-1., -params[1]])
		elif self._pdf == 'Bernoulli':
			return np.log(params/(1. - params))
		elif self._pdf == 'Beta':
			return np.array([params[0], params[1]])


class VariationalOptimizer(object):

	_chaos_model = None

	_data = None

	_W = None

	_Psi = None

	_prior_params = None
	# Number of observations 
	_K = None
	# L component
	_expL = None

	def __init__(self, chaos, data, W, prior_params):
		"""
		Initializes the object
		"""
		assert chaos._dim == W.shape[1]
		self._chaos_model = chaos
		self._data = data
		self._W = W
		self._Psi = self._chaos_model._basis(np.dot(W.T, self._data['xi'].T).T)
		self._prior_params = prior_params
		self._K = data['xi'].shape[0]

	def z_c_mean(self, omega):
		exp_F = ExponFam('Gamma')
		eta = exp_F.map_to_eta(omega)
		return np.array([0, (eta[0]+1) / (2*eta[1])])

	def z_tau(self):
		exp_F = ExponFam('Gamma')
		return exp_F.map_to_eta(self._prior_params['tau'])

	def z_omega(self):
		exp_F = ExponFam('Gamma')
		return exp_F.map_to_eta(self._prior_params['omega'])

	def update_Psi(self):
		self._Psi = self._chaos_model._basis(np.dot(self._W.T, self._data['xi'].T).T)

	def update_L(self):
		eta = np.dot(self._W.T, self._data['xi'].T).T
		self._L = np.array([self._K / 2., - np.linalg.norm(self._data['y'] - self._chaos_model.eval(eta) ) ** 2 / 2.])

	def expL(self, m, rho):
		eta = np.dot(self._W.T, self._data['xi'].T).T
		Psi = self._chaos_model._basis(eta)
		self._expL = np.array([self._K / 2., - np.linalg.norm(self._data['y'] - np.dot(Psi, m) ) ** 2 / 2. - np.sum(np.diag(np.dot(np.dot(Psi.T, Psi), np.diag(1/rho) )  / 2.) ) ])

	def compELBO(self, eta_c, eta_om, eta_tau):
		expF_gauss = ExponFam('Gauss')
		expF_gamma = ExponFam('Gamma')
		ELBO = - self._K * np.log(2*np.pi) / 2. + np.sum(expF_gamma.A_grad(eta_tau) * self._expL)
		for i in range(eta_c.shape[0]):
			ELBO += expF_gamma.A(eta_om[i,:]) - np.sum( (eta_om[i,:] - self.z_omega())* expF_gamma.A_grad(eta_om[i,:]) ) - expF_gamma.A(self.z_omega())
			omega = expF_gamma.map_from_eta(eta_om[i,:])
			ELBO += expF_gauss.A(eta_c[i,:]) - np.sum( eta_c[i,:] * expF_gauss.A_grad(eta_c[i,:]) ) - np.sum( self.z_c_mean(omega) * expF_gauss.A_grad(eta_c[i,:]) ) - (-sp.digamma(eta_om[i,0]+1) + np.log(-eta_om[i,0]) ) / 2.
		ELBO +=  - (eta_tau[0]+1.) * np.log(-eta_tau[1]) + (self.z_tau()[0]+1.) * np.log(-self.z_tau()[1]) - np.sum( eta_tau - self.z_tau() * np.array([sp.digamma(eta_tau[0]+1) - np.log(-eta_tau[1]) , -(eta_tau[0]+1)/eta_tau[1]]) )
		#print 'ELBO : ' + str(ELBO)
		return ELBO


	def optimize(self):
		expF_gauss = ExponFam('Gauss')
		expF_gamma = ExponFam('Gamma')
		eta_c = np.zeros((self._chaos_model._coeffs.shape[0],2))
		eta_om = np.zeros((self._chaos_model._coeffs.shape[0],2))
		for i in range(self._chaos_model._coeffs.shape[0]):
			eta_om[i,:] = self.z_omega()
			omega = expF_gamma.map_from_eta(eta_om[i,:])
			eta_c[i,:] = self.z_c_mean(omega)
		eta_tau = self.z_tau().reshape((1,2))
		elbo = np.array([-np.inf])

		eta_c_new = 1e+5 * np.ones(eta_c.shape)
		eta_om_new = 1e+5 * np.ones(eta_om.shape)
		eta_tau_new = 1e+5 * np.ones(eta_tau.shape)

		c_sol = np.zeros(eta_c.shape)
		omega_sol = np.zeros(eta_om.shape)
		tau_sol = np.zeros(eta_tau.shape)
		#print 'Eta_c :' + str(eta_c)
		err = 1e+6
		iters = 0
		while err > 1e-4:
			params_c = np.zeros(eta_c.shape)
			for i in range(params_c.shape[0]):
				params_c[i,:] = expF_gauss.map_from_eta(eta_c[i,:])
			self.expL(params_c[:,0], params_c[:,1])
			eta_tau_new = self.z_tau() + self._expL# - np.array([20., 0])
			print eta_tau_new
			print 'Updating tau'
			for i in range(eta_om.shape[0]):
				eta_om_new[i,:] = self.z_omega() + np.array([1., - expF_gauss.A_grad(eta_c[i,:])[1]]) / 2.
			print 'Updating omega'
			for i in range(eta_c.shape[0]):
				e_i = np.zeros(eta_c.shape[0])
				e_i[i] = 1.
				v_i = np.array([np.dot(self._data['y'].reshape(1, self._K), np.dot(self._Psi, e_i)), - np.sum(np.diag(np.dot(self._Psi.T, np.dot(self._Psi, np.diag(e_i))))) / 2. ])
				m_i = params_c[:,0].copy().reshape(eta_c.shape[0], 1)
				m_i[i,0] = 0.
				em_i = np.dot(e_i.reshape(eta_c.shape[0],1), m_i.T)
				u_i = np.array([- np.sum(np.diag( np.dot(self._Psi.T, np.dot(self._Psi, em_i)) )), 0])
				eta_c_new[i,:] = (v_i + u_i) * expF_gamma.A_grad(eta_tau_new)[1] + self.z_c_mean(eta_om_new[i,:])
				params_c[i,:] = expF_gauss.map_from_eta(eta_c_new[i,:])
			print 'Updating c'
			ETA = np.vstack([eta_tau, eta_om, eta_c])
			ETA_new = np.vstack([eta_tau_new, eta_om_new, eta_c_new])
			err = np.linalg.norm(ETA-ETA_new)
			print 'Relative error : ' + str(err)
			elbo = np.append(elbo, self.compELBO(eta_c_new, eta_om_new, eta_tau_new) )
			eta_c = eta_c_new.copy()
			eta_tau = eta_tau_new.copy()
			eta_om = eta_om_new.copy()
			iters += 1

		tau_sol[:] = expF_gamma.map_from_eta(eta_tau)
		for i in range(c_sol.shape[0]):
			c_sol[i,:] = expF_gauss.map_from_eta(eta_c[i,:])
			omega_sol[i,:] = expF_gamma.map_from_eta(eta_om[i,:])
			
		#print tau_sol
		#print c_sol
		#print omega_sol
		print 'Total number of iterations : ' + str(iters)
		return c_sol, omega_sol, tau_sol, elbo


class SparseVariationalOptimizer(object):

	_chaos_model = None

	_data = None

	_W = None # Won't be used. Delete it later. 

	_Psi = None

	_yPsi = None

	_PsiPsi = None

	_prior_params = None
	# Number of observations 
	_K = None
	# L component
	_expL = None

	def __init__(self, chaos, data, prior_params):
		"""
		Initializes the object
		"""
		self._chaos_model = chaos
		self._data = data
		self._Psi = self._chaos_model._basis(self._data['xi'])
		self._PsiPsi = np.dot(self._Psi.T, self._Psi)
		self._yPsi = (self._data['y'] * self._Psi.T).T
		self._prior_params = prior_params
		self._K = data['xi'].shape[0]

	def z_c_mean(self, val, arg = 'omega'):
		if arg == 'omega':
			exp_F = ExponFam('Gamma')
			eta = exp_F.map_to_eta(val)
		elif arg == 'eta_om':
			eta = val
		return np.array([0, (eta[0]+1) / (2*eta[1])])

	def z_z_mean(self, val, arg = 'pi'):
		exp_F = ExponFam('Beta')
		if arg == 'pi':
			eta = exp_F.map_to_eta(val)
		elif arg == 'eta_pi':
			eta = val
		return sp.digamma(eta[0]) - sp.digamma(eta[1])

	def z_tau(self):
		exp_F = ExponFam('Gamma')
		return exp_F.map_to_eta(self._prior_params['tau'])

	def z_omega(self):
		exp_F = ExponFam('Gamma')
		return exp_F.map_to_eta(self._prior_params['omega'])

	def z_pi(self):
		exp_F = ExponFam('Beta')
		return exp_F.map_to_eta(self._prior_params['pi'])

	def update_Psi(self): # Won't be used (most likely). Delete it later. 
		self._Psi = self._chaos_model._basis(self._data['xi'])

	def update_L(self):
		xi = self._data['xi']
		self._L = np.array([self._K / 2., - np.linalg.norm(self._data['y'] - self._chaos_model.eval(xi) ) ** 2 / 2.])

	def expL(self, m, rho, pi):
		eta = self._data['xi']
		Psi = self._chaos_model._basis(eta)
		self._expL = np.array([self._K / 2., - np.linalg.norm(self._data['y'] - np.dot(Psi, pi*m) ) ** 2 / 2. - 0.5 * np.trace( np.dot(self._PsiPsi, np.diag( pi*(1./rho) + (pi-pi**2)*m**2) )  )  ])

	def compELBO(self, eta_c, eta_om, eta_tau, eta_z, eta_pi):
		expF_gauss = ExponFam('Gauss')
		expF_gamma = ExponFam('Gamma')
		expF_beta = ExponFam('Beta')
		expF_bernoulli = ExponFam('Bernoulli')

		ELBO = - 0.5 * self._K * np.log(2*np.pi) + np.sum(expF_gamma.A_grad(eta_tau) * self._expL)
		# Expected log-likelihood
		for i in range(eta_c.shape[0]):
			# Adding entropy and expected log-prior of omega
			ELBO += expF_gamma.A(eta_om[i,:]) - np.sum( (eta_om[i,:] - self.z_omega())* expF_gamma.A_grad(eta_om[i,:]) ) - expF_gamma.A(self.z_omega())
			omega = expF_gamma.map_from_eta(eta_om[i,:])
			# Adding entropy and expected log-prior of c
			ELBO += expF_gauss.A(eta_c[i,:]) - np.sum( eta_c[i,:] * expF_gauss.A_grad(eta_c[i,:]) ) + np.sum( self.z_c_mean(omega) * expF_gauss.A_grad(eta_c[i,:]) ) - (-sp.digamma(eta_om[i,0]+1) + np.log(-eta_om[i,0]) ) / 2.
			# Adding entropy and expected log-prior of pi 
			ELBO += expF_beta.A(eta_pi[i,:]) - np.sum( (eta_pi[i,:] - self.z_pi()) * expF_beta.A_grad(eta_pi[i,:]) ) - expF_beta.A(self.z_pi())
			pi = expF_beta.map_from_eta(eta_pi[i,:])
			# Adding entropy and expected log-prior of z
			ELBO += expF_bernoulli.A(eta_z[i])  - eta_z[i] * expF_bernoulli.A_grad(eta_z[i])  + self.z_z_mean(pi) * expF_bernoulli.A_grad(eta_z[i])  - (sp.digamma(eta_pi[i,0]+eta_pi[i,1]) - sp.digamma(eta_pi[i,1]))
		ELBO +=  - (eta_tau[0]+1.) * np.log(-eta_tau[1]) + (self.z_tau()[0]+1.) * np.log(-self.z_tau()[1]) - np.sum( eta_tau - self.z_tau() * np.array([sp.digamma(eta_tau[0]+1) - np.log(-eta_tau[1]) , -(eta_tau[0]+1)/eta_tau[1]]) )
		# Adding entropy and expected log-prior of tau
		return ELBO

	#def elbo_grad(self, var):
		"""
		Computes the updating term of ELBO's natural gradient 
		corresponding to the variable var.
		"""




	def optimize(self, method = 'ascent', tol = 1e-3):
		expF_gauss = ExponFam('Gauss')
		expF_gamma = ExponFam('Gamma')
		expF_beta = ExponFam('Beta')
		expF_bernoulli = ExponFam('Bernoulli')

		if method == 'ascent':

			eta_c = np.zeros((self._chaos_model._coeffs.shape[0],2))
			eta_om = np.zeros((self._chaos_model._coeffs.shape[0],2))
			eta_z = np.zeros(self._chaos_model._coeffs.shape[0])
			eta_pi = np.zeros((self._chaos_model._coeffs.shape[0], 2))
			for i in range(self._chaos_model._coeffs.shape[0]):
				eta_om[i,:] = self.z_omega()
				omega = expF_gamma.map_from_eta(eta_om[i,:])
				eta_c[i,:] = self.z_c_mean(omega)
				eta_pi[i,:] = self.z_pi()
				pi = expF_beta.map_from_eta(eta_pi[i,:])
				eta_z[i] = self.z_z_mean(pi)

			eta_tau = self.z_tau().reshape((1,2))
			elbo = np.array([-np.inf])

			eta_c_new = 1e+5 * np.ones(eta_c.shape)
			eta_om_new = 1e+5 * np.ones(eta_om.shape)
			eta_tau_new = 1e+5 * np.ones(eta_tau.shape)
			eta_z_new = 1e+5 * np.ones(eta_z.shape)
			eta_pi_new = 1e+5 * np.ones(eta_pi.shape)

			c_sol = np.zeros(eta_c.shape)
			omega_sol = np.zeros(eta_om.shape)
			tau_sol = np.zeros(eta_tau.shape)
			z_sol = np.zeros(eta_z.shape)
			pi_sol = np.zeros(eta_pi.shape)
			#print 'Eta_c :' + str(eta_c)
			err = 1e+6
			iters = 0
			pi_sum_prev = 0
			pi_err = 1e+5

			active_indices = range(eta_c.shape[0])

			while err > tol:
				params_c = np.zeros(eta_c.shape)
				params_z = np.zeros(eta_z.shape)
				
				for i in range(params_c.shape[0]):
					params_c[i,:] = expF_gauss.map_from_eta(eta_c[i,:])
					params_z[i] = expF_bernoulli.map_from_eta(eta_z[i])
				self.expL(params_c[:,0], params_c[:,1], params_z)
				# ---- Updating tau
				eta_tau_new = self.z_tau() + self._expL# - np.array([20., 0])

				for i in active_indices:#range(eta_om.shape[0]):
					# ---- Updating omega
					eta_om_new[i,:] = self.z_omega() + 0.5 * np.array([1., - expF_gauss.A_grad(eta_c[i,:])[1]])

				#for i in range(eta_om.shape[0]):
					# ---- Updating pi 
					eta_pi_new[i,:] = self.z_pi() + np.array([0, 1]) + np.array([ 1., -1.]) * expF_bernoulli.A_grad(eta_z[i])

				#for i in range(eta_c.shape[0]):
					# ---- Updating zeta
					v_i = np.sum( self._yPsi[:,i] * params_c[i,0]) - 0.5 * self._PsiPsi[i,i] * ( (1 - 2*params_z[i]) * params_c[i,0]**2)# + params_c[i,1])
					m_i = params_z * params_c[:,0].copy()#).reshape(eta_c.shape[0], 1)
					u_i = - np.sum( self._PsiPsi[i,:] * m_i) * params_c[i,0]
					eta_z_new[i] = (v_i + u_i) * expF_gamma.A_grad(eta_tau_new)[1] + self.z_z_mean(eta_pi_new[i,:], arg = 'eta_pi')
					params_z[i] = expF_bernoulli.map_from_eta(eta_z_new[i])


				#for i in range(eta_c.shape[0]):
					# ---- Updating c
					v_i = np.array([np.sum( self._yPsi[:,i]) * params_z[i], - 0.5 * self._PsiPsi[i,i] * params_z[i]]) ## testing 
					m_i = params_z * params_c[:,0].copy()#.reshape(eta_c.shape[0], 1)
					m_i[i] = 0.
					u_i = np.array([- np.sum(self._PsiPsi[i,:] * m_i) * params_z[i], 0 ])
					eta_c_new[i,:] = (v_i + u_i) * expF_gamma.A_grad(eta_tau_new)[1] + self.z_c_mean(eta_om_new[i,:], arg = 'eta_om')
					params_c[i,:] = expF_gauss.map_from_eta(eta_c_new[i,:])


			

				ETA = np.hstack([eta_tau.flatten(), eta_c.flatten(), eta_z ])
				ETA_new = np.hstack([eta_tau_new.flatten(), eta_c_new.flatten(), eta_z_new ])
				ZETA_err = np.sum( expF_bernoulli.map_from_eta(eta_z) - expF_bernoulli.map_from_eta(eta_z_new) )
				pi_sum_new = expF_bernoulli.map_from_eta(eta_z_new).sum()
				pi_err =  np.abs(pi_sum_prev - pi_sum_new)
				print pi_err
				pi_sum_prev = pi_sum_new.copy()

				if pi_err < 1e-4 and iters > 100:
					active_indices = list(np.where(expF_bernoulli.map_from_eta(eta_z_new) > .01)[0])
					print '----- Iterating only on sparse terms -----'
					#print active_indices

				#print ZETA_err
				err = np.linalg.norm(ETA-ETA_new)
				if iters%10==0:
					print 'Iters = '+str(iters) + ' '*10+ 'Relative error : ' + str(err) + ' '*10# + 'ELBO value: ' + str(elbo[iters])
				elbo = np.append(elbo, self.compELBO(eta_c_new, eta_om_new, eta_tau_new, eta_z_new, eta_pi_new) )
				eta_c = eta_c_new.copy()
				eta_tau = eta_tau_new.copy()
				eta_om = eta_om_new.copy()
				eta_z = eta_z_new.copy()
				eta_pi = eta_pi_new.copy()
				iters += 1


			tau_sol[:] = expF_gamma.map_from_eta(eta_tau)
			for i in range(c_sol.shape[0]):
				c_sol[i,:] = expF_gauss.map_from_eta(eta_c[i,:])
				omega_sol[i,:] = expF_gamma.map_from_eta(eta_om[i,:])
				z_sol[i] = expF_bernoulli.map_from_eta(eta_z[i])
				pi_sol[i,:] = expF_beta.map_from_eta(eta_pi[i,:])

			ZETA_err = np.sum(z_sol)

			#print omega_sol
			print 'Total number of iterations : ' + str(iters)
			return c_sol, omega_sol, tau_sol, z_sol, pi_sol, iters, elbo

		#elif method == 'stoch_ascent':



