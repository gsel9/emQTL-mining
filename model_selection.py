# -*- coding: utf-8 -*-
#
# model_selection.py
#

"""
Model selection framework.

The framework applies models with different hyperparemeter settings to classes
of test data. For each model, the the Jaccard coefficient and the time
complexity is recorded.
size.

"""

__author__ = 'Severin E. R. Langberg'
__email__ = 'Langberg91@gmail.no'


import operator

import numpy as np
import pandas as pd

from sklearn.model_selection import GridSearchCV
from sklearn.utils.validation import check_array
from sklearn.metrics import consensus_score
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.datasets import samples_generator as sgen

from sklearn.preprocessing import StandardScaler


class PerformanceTracker:
    """Determines the optimal algorithm for each class of test data.

    Args:
        test_classes (list of str): The labels for each class of test data.
        models (list of str): The labels for each model included in the
            experiment.

    """

    def __init__(self, test_classes, models):

        self.test_classes = test_classes
        self.models = models

        # NOTE: Attribute set with instance
        self.model_scores = self._setup_model_score_stats()
        self.winning_stats = self._setup_model_win_stats()

    def _setup_model_score_stats(self):
        # Returns an object that logs winning model score for each class of
        # test data.

        _model_stats = {}
        for test_class in self.test_classes:
            _model_stats[test_class] = {
                model: [] for model in self.models
            }

        return _model_stats

    def _setup_model_win_stats(self):
        # Returns an object that counts model wins for each class of test data.

        _model_stats = {}
        for test_class in self.test_classes:
            _model_stats[test_class] = {
                model: 0 for model in self.models
            }

        return _model_stats

    def update_stats(self, results):
        """Updates the counter for how many times a model has been
        voted optimal for a particular test data class."""

        for test_class in self.test_classes:
            name, _, score = results[test_class]
            self.winning_stats[test_class][name] += 1
            self.model_scores[test_class][name].append(score)

        return self

    @property
    def winner_models(self):
        """Determines the optimal model for each class of test data."""

        winners = {}
        for test_class in self.test_classes:
            candidates = self.winning_stats[test_class]
            winner, _ = max(candidates.items(), key=operator.itemgetter(1))
            winners[test_class] = winner

        return winners


class Experiment:
    """Perform experiments by applying an algorithm to data and measure the
    performance.

    Args:
        data (array-like):
        rows (array-like):
        cols (array-like):

    """

    def __init__(self, models_and_params, verbose=1, random_state=None):

        self.models_and_params = models_and_params
        self.verbose = verbose
        self.random_state = random_state

        # NOTE: Necessary to scale data to avoid sklearn inf/NaN error.
        self.scaler = StandardScaler()

        # NOTE: A cross val split producing only train and no test split.
        self.dummy_cv = [(slice(None), slice(None))]

        # NOTE: Attributes set with instance.
        self.results = None

        self._data = None
        self._rows = None
        self._cols = None

    def execute(self, data, indicators, target='score'):
        """Performs model comparison for each class of test data."""

        rows, cols = indicators

        if self.verbose > 0:
            print('Experiment initiated:\n{}'.format('-' * 21))

        self.results, self.grids = {}, []
        for key in data.keys():

            if self.verbose > 0:
                print('Training set: `{}`'.format(key))

            self._data = data[key]
            self._rows, self._cols = rows[key], cols[key]

            # Winning model, hest hparams, best score
            self.results[key] = self.compare_models(target=target)

            if self.verbose > 0:
                name, _, score = self.results[key]
                print('Best model: {}\nScore: {}\n'.format(name, score))

        return self

    def compare_models(self, target):
        """Compare model performance on target basis."""

        # Evaluates model performance by score value.
        if target == 'score':
            return self.score_eval()
        # Evaluates model performance by time complexity.
        elif target == 'time':
            return self.time_eval()
        else:
            raise ValueError('Invalid target: `{}`'.format(target))

        return self

    def score_eval(self):
        """Compare the model performance with respect to a score metric."""

        _train, self.row_idx, self.col_idx = sgen._shuffle(
            self._data, random_state=self.random_state
        )
        _train_std = self.scaler.fit_transform(_train)

        winning_model, best_params, best_score = None, None, -np.float('inf')
        for model, param_grid in self.models_and_params:

            # Determine the best hyperparameter combo for that model
            grid = GridSearchCV(
                model(random_state=self.random_state), param_grid,
                scoring=self.jaccard, cv=self.dummy_cv,
                return_train_score=True, refit=False
            )
            grid.fit(_train_std, y=None)

            if self.verbose > 1:
                print('Model performance:\nName: {}\nScore: {}\n'
                      ''.format(model.__name__, grid.best_score_))

            if grid.best_score_ > best_score:
                best_score = grid.best_score_
                winner_name = model.__name__
                winner_model = model(**grid.best_params_)

        return (winner_name, winner_model, best_score)

    def jaccard(self, estimator, train=None):
        """Computes the Jaccard coefficient as a measure of similarity between
        two sets of biclusters.

        Args:
            estimator ():
            train: Ignored

        Returns:
            (float): The Jaccard coefficient value.

        """

        rows, cols = estimator.biclusters_
        if len(rows) == 0 or len(cols) == 0:
            return 0.0
        else:
            ytrue = (self._rows[:, self.row_idx], self._cols[:, self.col_idx])
            return consensus_score((rows, cols), ytrue)


    # NOTE:
    # * Not performing grid search, but only logging time of fitting
    #   model to data?
    def time_eval(self):

        pass


class MultiExperiment(Experiment):

    def __init__(self, models_and_params, nruns=1, verbose=1, random_state=1):

        super().__init__(models_and_params, verbose, random_state)

        self.nruns = nruns

        # NOTE:
        self._tracker = None
        self._multi_results = None

    @property
    def best_models(self):

        return self.results

    @property
    def class_winners(self):

        return self._tracker.winner_models

    @property
    def model_votes(self):

        return self._tracker.winning_stats

    @property
    def performance_report(self):

        score_stats, test_classes = [], []
        for test_class, winner in self.class_winners.items():

            win_scores = self._tracker.model_scores[test_class][winner]
            score_stats.append(
                (winner, np.mean(win_scores), np.std(win_scores))
            )
            test_classes.append(test_class)

        _report = pd.DataFrame(
            score_stats, columns=['model', 'avg score', 'std score'],
            index=test_classes
        )
        _report.index.name = 'test_class'

        return _report

    @property
    def model_labels(self):

        return [model.__name__ for model, _ in self.models_and_params]

    def execute_all(self, dataset, test_classes, target='score'):

        self._tracker = PerformanceTracker(test_classes, self.model_labels)
        for run_num in range(self.nruns):

            if self.verbose > 0:
                print('Experiment parallel number: {}'.format(run_num + 1))

            # Perform single experiment with dataset.
            for class_num, (data, rows, cols) in enumerate(dataset):

                if self.verbose > 0:
                    print('Test class number: {}'.format(class_num + 1))

                # Perform model comparison with test data class.
                self.execute(data, (rows, cols), target=target)

                # NOTE: Num wins counter is continued for each run.
                self._tracker.update_stats(self.results)

        return self


if __name__ == '__main__':

    import testsets
    import pandas as pd

    from sklearn.cluster import SpectralBiclustering
    from sklearn.cluster import SpectralCoclustering

    SEED = 0

    data_feats = pd.read_csv(
        './../data/data_characteristics.csv', sep='\t', index_col=0
    )
    array_size = (1000, 100)
    var_num_clusters = [2, 4, 8]
    # NOTE: Each list element is a tuple of data, rows, cols
    cluster_exp_data = [
        testsets.gen_test_sets(
            data_feats, sparse=[False, True, False, True],
            non_neg=[False, True, False, True],
            shape=array_size, n_clusters=n_clusters, seed=0
        )
        for n_clusters in var_num_clusters
    ]

    skmodels_and_params = [
    (
        SpectralBiclustering, {
            'n_clusters': var_num_clusters, 'method': ['log', 'bistochastic'],
            'n_components': [6, 9, 12], 'n_best': [3, 6]
        }
    ),
    (
        SpectralCoclustering, {'n_clusters': var_num_clusters}
    )
]

    sk_multi_exper = MultiExperiment(skmodels_and_params, verbose=0)
    sk_multi_exper.execute_all(cluster_exp_data, data_feats.index)
    print(sk_multi_exper.best_models)
    print(sk_multi_exper.class_winners)
    print(sk_multi_exper.performance_report)
    print(sk_multi_exper.model_votes)

    # Collects:
    # * Names and num wins of each model : num_model_wins
    # * The winner models with hparams for each test class: best_models
    # * The scores for each winner model: winner_stats
