"""
This module provides the most basic neural net layers. This goes from an input to an output with an optional activation.
"""
# standard libraries
import logging
# third party libraries
import theano.tensor as T
import theano.sandbox.rng_mrg as RNG_MRG
# internal references
from opendeep.utils.constructors import sharedX
from opendeep.utils.decorators import inherit_docs
from opendeep.models.model import Model
from opendeep.utils.nnet import get_weights, get_bias
from opendeep.utils.activation import get_activation_function
from opendeep.utils.cost import get_cost_function
from opendeep.utils.noise import get_noise

log = logging.getLogger(__name__)


@inherit_docs
class Dense(Model):
    """
    This is your basic input -> nonlinear(output) layer. No hidden representation. It is also known as a
    fully-connected layer.
    """
    def __init__(self, inputs_hook=None, params_hook=None, outdir='outputs/basic',
                 input_size=None, output_size=None,
                 activation='rectifier',
                 cost='mse', cost_args=None,
                 weights_init='uniform', weights_mean=0, weights_std=5e-3, weights_interval='montreal',
                 bias_init=0.0,
                 noise=None, noise_level=None, mrg=RNG_MRG.MRG_RandomStreams(1),
                 **kwargs):
        """
        Initialize a basic layer.

        Parameters
        ----------
        inputs_hook : Tuple of (shape, variable)
            Routing information for the model to accept inputs from elsewhere. This is used for linking
            different models together. For now, it needs to include the shape information (normally the
            dimensionality of the input i.e. input_size).
        params_hook : List(theano shared variable)
            A list of model parameters (shared theano variables) that you should use when constructing
            this model (instead of initializing your own shared variables). This parameter is useful when you want to
            have two versions of the model that use the same parameters - such as a training model with dropout applied
            to layers and one without for testing, where the parameters are shared between the two.
        outdir : str
            The directory you want outputs (parameters, images, etc.) to save to. If None, nothing will
            be saved.
        input_size : int
            The size (dimensionality) of the input to the layer. If shape is provided in `inputs_hook`,
            this is optional.
        output_size : int
            The size (dimensionality) of the output from the layer.
        activation : str or callable
            The activation function to use after the dot product going from input -> output. This can be a string
            representing an option from opendeep.utils.activation, or your own function as long as it is callable.
        cost : str or callable
            The cost function to use when training the layer. This should be appropriate for the output type, i.e.
            mse for real-valued outputs, binary cross-entropy for binary outputs, etc.
        cost_args : dict
            Any additional named keyword arguments to pass to the specified `cost_function`.
        weights_init : str
            Determines the method for initializing input -> output weights. See opendeep.utils.nnet for options.
        weights_interval : str or float
            If Uniform `weights_init`, the +- interval to use. See opendeep.utils.nnet for options.
        weights_mean : float
            If Gaussian `weights_init`, the mean value to use.
        weights_std : float
            If Gaussian `weights_init`, the standard deviation to use.
        bias_init : float
            The initial value to use for the bias parameter. Most often, the default of 0.0 is preferred.
        noise : str
            What type of noise to use for corrupting the output (if not None). See opendeep.utils.noise
            for options. This should be appropriate for the output activation, i.e. Gaussian for tanh or other
            real-valued activations, etc. Often, you will use 'dropout' here as a regularization in BasicLayers.
        noise_level : float
            The amount of noise to use for the noise function specified by `noise`. This could be the
            standard deviation for gaussian noise, the interval for uniform noise, the dropout amount, etc.
        mrg : random
            A random number generator that is used when adding noise.
            I recommend using Theano's sandbox.rng_mrg.MRG_RandomStreams.
        """
        # init Model to combine the defaults and config dictionaries with the initial parameters.
        initial_parameters = locals().copy()
        initial_parameters.pop('self')
        super(Dense, self).__init__(**initial_parameters)

        ##################
        # specifications #
        ##################
        # grab info from the inputs_hook, or from parameters
        if inputs_hook is not None:  # inputs_hook is a tuple of (Shape, Input)
            assert len(inputs_hook) == 2, 'Expected inputs_hook to be tuple!'  # make sure inputs_hook is a tuple
            self.input = inputs_hook[1]
        else:
            # make the input a symbolic matrix
            self.input = T.matrix('X')

        # now that we have the input specs, define the output 'target' variable to be used in supervised training!
        if kwargs.get('out_as_probs') == False:
            self.target = T.vector('Y', dtype='int64')
        else:
            self.target = T.matrix('Y')

        # either grab the output's desired size from the parameter directly, or copy input_size
        self.output_size = self.output_size or self.input_size

        # other specifications
        # activation function!
        activation_func = get_activation_function(activation)
        # cost function!
        cost_func = get_cost_function(cost)
        cost_args = cost_args or dict()

        ####################################################
        # parameters - make sure to deal with params_hook! #
        ####################################################
        if params_hook is not None:
            # make sure the params_hook has W (weights matrix) and b (bias vector)
            assert len(params_hook) == 2, \
                "Expected 2 params (W and b) for Dense, found {0!s}!".format(len(params_hook))
            W, b = params_hook
        else:
            W = get_weights(weights_init=weights_init,
                            shape=(self.input_size, self.output_size),
                            name="W",
                            rng=mrg,
                            # if gaussian
                            mean=weights_mean,
                            std=weights_std,
                            # if uniform
                            interval=weights_interval)

            # grab the bias vector
            b = get_bias(shape=output_size, name="b", init_values=bias_init)

        # Finally have the two parameters - weights matrix W and bias vector b. That is all!
        self.params = [W, b]

        ###############
        # computation #
        ###############
        # Here is the meat of the computation transforming input -> output
        # It simply involves a matrix multiplication of inputs*weights, adding the bias vector, and then passing
        # the result through our activation function (normally something nonlinear such as: max(0, output))
        self.output = activation_func(T.dot(self.input, W) + b)

        # Now deal with noise if we added it:
        if noise:
            log.debug('Adding noise switch.')
            if noise_level is not None:
                noise_func = get_noise(noise, noise_level=noise_level, mrg=mrg)
            else:
                noise_func = get_noise(noise, mrg=mrg)
            # apply the noise as a switch!
            # default to apply noise. this is for the cost and gradient functions to be computed later
            # (not sure if the above statement is accurate such that gradient depends on initial value of switch)
            self.switch = sharedX(value=1, name="basiclayer_noise_switch")
            self.output = T.switch(self.switch,
                                   noise_func(input=self.output),
                                   self.output)

        # now to define the cost of the model - use the cost function to compare our output with the target value.
        self.cost = cost_func(output=self.output, target=self.target, **cost_args)

        log.debug("Initialized a basic fully-connected layer with shape %s and activation: %s",
                  str((self.input_size, self.output_size)), str(activation))

    def get_inputs(self):
        return [self.input]

    def get_outputs(self):
        return self.output

    def get_targets(self):
        return [self.target]

    def get_train_cost(self):
        return self.cost

    def get_noise_switch(self):
        if hasattr(self, 'switch'):
            return self.switch
        else:
            return []

    def get_params(self):
        return self.params

    def save_args(self, args_file="basiclayer_config.pkl"):
        super(Dense, self).save_args(args_file)


@inherit_docs
class SoftmaxLayer(Dense):
    """
    The softmax layer is meant as a last-step prediction layer using the softmax activation function -
    this class exists to provide easy access to methods for errors and log-likelihood for a given truth label y.

    It is a special subclass of the Dense (a fully-connected layer),
    with the activation function forced to be 'softmax'
    """
    def __init__(self, inputs_hook=None, params_hook=None, outdir='outputs/softmax',
                 input_size=None, output_size=None,
                 cost='nll', cost_args=None,
                 weights_init='uniform', weights_mean=0, weights_std=5e-3, weights_interval='montreal',
                 bias_init=0.0,
                 out_as_probs=False,
                 **kwargs):
        """
        Initialize a Softmax layer.

        Parameters
        ----------
        inputs_hook : Tuple of (shape, variable)
            Routing information for the model to accept inputs from elsewhere. This is used for linking
            different models together. For now, you need to include the shape information (normally the
            dimensionality of the input i.e. input_size).
        params_hook : List(theano shared variable)
            A list of model parameters (shared theano variables) that you should use when constructing
            this model (instead of initializing your own shared variables). This parameter is useful when you want to
            have two versions of the model that use the same parameters - such as a training model with dropout applied
            to layers and one without for testing, where the parameters are shared between the two.
        outdir : str
            The directory you want outputs (parameters, images, etc.) to save to. If None, nothing will
            be saved.
        input_size : int
            The size (dimensionality) of the input to the layer. If shape is provided in `inputs_hook`,
            this is optional.
        output_size : int
            The size (dimensionality) of the output from the layer. This is normally the number of separate
            classification classes you have.
        cost : str or callable
            The cost function to use when training the layer. This should be appropriate for the output type, i.e.
            mse for real-valued outputs, binary cross-entropy for binary outputs, etc.
        cost_args : dict
            Any additional named keyword arguments to pass to the specified `cost_function`.
        weights_init : str
            Determines the method for initializing input -> output weights. See opendeep.utils.nnet for options.
        weights_interval : str or float
            If Uniform `weights_init`, the +- interval to use. See opendeep.utils.nnet for options.
        weights_mean : float
            If Gaussian `weights_init`, the mean value to use.
        weights_std : float
            If Gaussian `weights_init`, the standard deviation to use.
        bias_init : float
            The initial value to use for the bias parameter. Most often, the default of 0.0 is preferred.
        out_as_probs : bool
            Whether to output the argmax prediction (the predicted class of the model), or the probability distribution
            over all classes. True means output the distribution of size `output_size` and False means output a single
            number index for the class that had the highest probability.
        """
        if cost == 'nll':
            cost_args = cost_args or dict()
            cost_args['one_hot'] = out_as_probs
        # init the fully connected generic layer with a softmax activation function
        super(SoftmaxLayer, self).__init__(inputs_hook=inputs_hook,
                                           params_hook=params_hook,
                                           activation='softmax',
                                           cost=cost,
                                           cost_args=cost_args,
                                           input_size=input_size,
                                           output_size=output_size,
                                           weights_init=weights_init,
                                           weights_mean=weights_mean,
                                           weights_std=weights_std,
                                           weights_interval=weights_interval,
                                           bias_init=bias_init,
                                           out_as_probs=out_as_probs,
                                           outdir=outdir,
                                           noise=False)
        # the outputs of the layer are the probabilities of being in a given class
        self.p_y_given_x = super(SoftmaxLayer, self).get_outputs()
        self.y_pred = T.argmax(self.p_y_given_x, axis=1)

        if out_as_probs:
            self.output = self.p_y_given_x
        else:
            self.output = self.y_pred

        self.out_as_probs = out_as_probs

    def get_monitors(self):
        # grab the basiclayer's monitors
        monitors = super(SoftmaxLayer, self).get_monitors()
        # add the 'error' monitor.
        monitors.update({'softmax_error': self.errors()})
        return monitors

    def errors(self):
        """
        Return a float representing the number of errors in the minibatch
        over the total number of examples of the minibatch; zero-one
        loss over the size of the minibatch.

        Returns
        -------
        float
            The error amount.
        """
        if self.out_as_probs:
            return T.mean(T.neq(self.y_pred, T.argmax(self.target, axis=1)))
        # the T.neq operator returns a vector of 0s and 1s, where 1
        # represents a mistake in prediction
        return T.mean(T.neq(self.y_pred, self.target))

    def get_argmax_prediction(self):
        """
        Returns the index of the class with the highest probability output.

        Returns
        -------
        int
            Index of the class with the highest probability.
        """
        # return the argmax y_pred class
        return self.y_pred

    def save_args(self, args_file="softmax_config.pkl"):
        super(SoftmaxLayer, self).save_args(args_file)