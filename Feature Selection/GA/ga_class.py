from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.model_selection import cross_val_score
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted
from sklearn.externals import six
from random import sample
from random import randint
import random


from deap import base, creator
from deap import tools

import numpy as np

from itertools import compress
from datetime import datetime
from abc import ABCMeta
from warnings import warn

def safe_mask(X, mask):
    """Return a mask which is safe to use on X.
    Parameters
    ----------
    X : {array-like, sparse matrix}
        Data on which to apply mask.
    mask : array
        Mask to be used on X.
    Returns
    -------
        mask
    """
    mask = np.asarray(mask)
    if np.issubdtype(mask.dtype, np.int):
        return mask

    if hasattr(X, "toarray"):
        ind = np.arange(mask.shape[0])
        mask = ind[mask]
    return mask


class SelectorMixin(six.with_metaclass(ABCMeta, TransformerMixin)):
    """
    Transformer mixin that performs feature selection given a support mask
    This mixin provides a feature selector implementation with `transform` and
    `inverse_transform` functionality given an implementation of
    `_get_support_mask`.
    """

    def get_support(self, indices=False):
        """
        Get a mask, or integer index, of the features selected
        Parameters
        ----------
        indices : boolean (default False)
            If True, the return value will be an array of integers, rather
            than a boolean mask.
        Returns
        -------
        support : array
            An index that selects the retained features from a feature vector.
            If `indices` is False, this is a boolean array of shape
            [# input features], in which an element is True iff its
            corresponding feature is selected for retention. If `indices` is
            True, this is an integer array of shape [# output features] whose
            values are indices into the input feature vector.
        """
        mask = self._get_support_mask()
        return mask if not indices else np.where(mask)[0]

    def _get_support_mask(self):
        """
        Get the boolean mask indicating which features are selected
        Returns
        -------
        support : boolean array of shape [# input features]
            An element is True iff its corresponding feature is selected for
            retention.
        """

    def transform(self, X):
        """Reduce X to the selected features.
        Parameters
        ----------
        X : array of shape [n_samples, n_features]
            The input samples.
        Returns
        -------
        X_r : array of shape [n_samples, n_selected_features]
            The input samples with only the selected features.
        """
        X = check_array(X, accept_sparse='csr')
        mask = self.get_support()
        if not mask.any():
            warn("No features were selected: either the data is"
                 " too noisy or the selection test too strict.",
                 UserWarning)
            return np.empty(0).reshape((X.shape[0], 0))
        if len(mask) != X.shape[1]:
            raise ValueError("X has a different shape than during fitting.")
        return X[:, safe_mask(X, mask)]

class _BaseFilter(BaseEstimator, SelectorMixin):
    """Initialize the univariate feature selection.
    Parameters
    ----------
    score_func : callable
        Function taking two arrays X and y, and returning a pair of arrays
        (scores, pvalues) or a single array with scores.
    """

    def __init__(self, score_func):
        self.score_func = score_func

    def fit(self, X, y):
        """Run score function on (X, y) and get the appropriate features.
        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            The training input samples.
        y : array-like, shape = [n_samples]
            The target values (class labels in classification, real numbers in
            regression).
        Returns
        -------
        self : object
            Returns self.
        """
        X, y = check_X_y(X, y, ['csr', 'csc'], multi_output=True)

        if not callable(self.score_func):
            raise TypeError("The score function should be a callable, %s (%s) "
                            "was passed."
                            % (self.score_func, type(self.score_func)))

        self._check_params(X, y)
        score_func_ret = self.score_func(X, y)
        if isinstance(score_func_ret, (list, tuple)):
            self.scores_, self.pvalues_ = score_func_ret
            self.pvalues_ = np.asarray(self.pvalues_)
        else:
            self.scores_ = score_func_ret
            self.pvalues_ = None

        self.scores_ = np.asarray(self.scores_)

        return self

    def _check_params(self, X, y):
        pass
    

    
class genetic_algorithm(_BaseFilter):
    
    def __init__(self, estimator,score_func = lambda x:x, X=None, y=None, cross_over_prob = 0.2, individual_mutation_probability = 0.05, gene_mutation_prob = 0.05, number_gen = 20, size_pop = 40):
        self.mutation_prob = individual_mutation_probability
        self.number_gen = number_gen
        self.cross_over_prob = 0.2
        self.size_pop = size_pop
        self.score_func = score_func
        self.estimator = estimator
    
        creator.create("FitnessMin", base.Fitness, weights=(1.0, -1.0))
        creator.create("Individual", list, fitness=creator.FitnessMin)
        
        self.toolbox = base.Toolbox()
        self.toolbox.register("attribute", self._gen_in)
        self.toolbox.register("individual", tools.initIterate, creator.Individual,
                         self.toolbox.attribute)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", tools.mutUniformInt,low = 0, up = 1, indpb = gene_mutation_prob)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
        self.toolbox.register("map", map)

        self.stats = tools.Statistics(lambda ind: ind.fitness.values)
        self.stats.register("avg", np.mean)
        self.stats.register("std", np.std)
        self.stats.register("min", np.min)
        self.stats.register("max", np.max)

        self.logbook = tools.Logbook()
        self.logbook.header = ["gen"] + self.stats.fields        
        
        print("Got data")
        self.toolbox.register("evaluate", self._evaluate, X = X, y = y)        
        
    def fit(self,X,y):

        self.n_features = len(X)   
        self.toolbox.register("evaluate", self._evaluate, X = X, y = y)        
        
        pop = self.toolbox.population(self.size_pop) 
        hof = tools.HallOfFame(1)

        # Evaluate the entire population
        print("Fit")
        fitnesses = self.toolbox.map(self.toolbox.evaluate, pop)
        for ind, fit in zip(pop, fitnesses):
            ind.fitness.values = fit
        
        print("Starting")
        for g in range(self.number_gen):
            # Select the next generation individuals
            offspring = self.toolbox.select(pop, len(pop))
            # Clone the selected individuals
            offspring = list(map(self.toolbox.clone, offspring)) 
        
            # Apply crossover and mutation on the offspring
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < self.cross_over_prob:
                    self.toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values
        
            for mutant in offspring:
                if random.random() < self.mutation_prob:
                    self.toolbox.mutate(mutant)
                    del mutant.fitness.values
        
            # Evaluate the individuals with an invalid fitness ( new individuals)
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = self.toolbox.map(self.toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
        
            # The population is entirely replaced by the offspring
            pop[:] = offspring
            
            # Log statistic
            hof.update(pop)
            self.logbook.record(gen=g, **self.stats.compile(pop))
            print("Generation: ", g + 1 , "/", self.number_gen, "TIME: ", datetime.now().time().minute, ":", datetime.now().time().second)
        
        self.mask = hof[0][:]
        self.fitness = hof[0].fitness.values
    
            
    def _gen_in(self):
        RND = randint(0,self.n_features)
        
        return   sample(list(np.concatenate( (np.zeros([self.n_features-RND,], dtype=int), np.ones([RND,], dtype=int)), axis = 0)), self.n_features)

        # Evaluation Function 
    def _evaluate(self, individual, X, y, cv = 3):

        # Select Features
        features = list( compress( range(len(individual)), individual))
        train =  np.reshape([X[:, i] for i in features], [ len(features),  len(X)]).T
        
        if( len(train) == 0 ):
            return 0,
               
        # Applying K-Fold Cross Validation
        print("cross")
        accuracies = cross_val_score( estimator = clone(self.estimator) , X = train, y = y, cv = 3)
        
        return accuracies.mean() - accuracies.std(), pow(sum(individual)/(len(X)*5),2),

    def transform(self,X):
        features = list( compress( range(len(self.mask)), self.mask))
        return np.reshape([X[:, i] for i in features], [ len(features),  len(X)]).T

    def _get_support_mask(self):
        check_is_fitted(self, 'support_')
        return self.support_