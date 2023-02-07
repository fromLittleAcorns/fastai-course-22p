# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/09_Learner.ipynb.

# %% auto 0
__all__ = ['DataLoaders', 'CancelFitException', 'CancelBatchException', 'CancelEpochException', 'run_cbs', 'Callback',
           'SingleBatchCB', 'DeviceCB', 'to_cpu', 'MetricsCB', 'Learner', 'ProgressCB', 'TrainCB', 'with_cbs',
           'TrainLearner', 'MomentumLearner', 'LRFinderCB', 'lr_find']

# %% ../nbs/09_Learner.ipynb 1
import pickle,gzip,math,os,time,shutil,torch,matplotlib as mpl,numpy as np,matplotlib.pyplot as plt
import fastcore.all as fc
from collections.abc import Mapping
from pathlib import Path
from operator import attrgetter,itemgetter
from functools import partial
from copy import copy
from contextlib import contextmanager

from torch import tensor,nn,optim
from torch.utils.data import DataLoader,default_collate
import torch.nn.functional as F
import torchvision.transforms.functional as TF
from datasets import load_dataset,load_dataset_builder

from .datasets import *
from .conv import *

from fastprogress import progress_bar,master_bar

# %% ../nbs/09_Learner.ipynb 10
class DataLoaders:
    """ Class to create train and validate dataloaders from a dataset
    """
    
    def __init__(self, *dls): self.train, self.valid = dls[:2]
    
    @classmethod
    def from_dd(cls, dd, batch_size, as_tuple=True, **kwargs):
        """Return a tuple of dataloaders from the dd dataset
        """
        return cls(*[DataLoader(ds, batch_size, collate_fn=collate_dict(ds), **kwargs) for ds in dd.values()]) 

# %% ../nbs/09_Learner.ipynb 17
class CancelFitException(Exception): pass
class CancelBatchException(Exception): pass
class CancelEpochException(Exception): pass

# %% ../nbs/09_Learner.ipynb 18
def run_cbs(cbs, method_nm, learn=None):
    for cb in sorted(cbs, key=attrgetter('order')):
        # if there is a callback with the name then return it else return None
        method = getattr(cb, method_nm, None)
        # if the callback is not None then execute it
        if method is not None: method(learn)

# %% ../nbs/09_Learner.ipynb 20
class Callback(): order = 0

# %% ../nbs/09_Learner.ipynb 28
class SingleBatchCB(Callback):
    order = 1
    def after_batch(self, learn): raise CancelFitException()

# %% ../nbs/09_Learner.ipynb 37
class DeviceCB(Callback):
    def __init__(self, device=def_device): fc.store_attr()
    def before_fit(self, learn):
        if hasattr(learn.model, 'to'): learn.model.to(self.device)
    def before_batch(self, learn):
        learn.batch = to_device(learn.batch, device=self.device)

# %% ../nbs/09_Learner.ipynb 40
from torcheval.metrics import MulticlassAccuracy, Mean

# %% ../nbs/09_Learner.ipynb 45
def to_cpu(x):
    """recursive function that breaks lists and tuples into individual items moves them to the cpu
    and then returns the original item with all of the parts moved
    """
    if isinstance(x, Mapping): return {k: to_cpu(v) for k, v in x.items()}
    if isinstance(x, list): return [to_cpu(v) for v in x]
    if isinstance(x, tuple): return tuple(to_cpu(list(x)))
    return x.detach().cpu()

# %% ../nbs/09_Learner.ipynb 46
class MetricsCB(Callback):
    def __init__(self, *ms, **metrics):
        # Assign all metrics supplied as list items to attributes
        for o in ms:
            # Create a metrics dictionary to facilitate easy access
            metrics[type(o).__name__()] = o
        self.metrics = metrics
        self.all_metrics = copy(metrics)
        self.all_metrics['loss'] = self.loss = Mean()

    def _log(self, 
             d # list of metrics to print for each epoch
            ):
        """ Print summary of the logs every epoch
        """
        print(d)
        
    def before_fit(self, learn):
        # Assign this metrics instance to the learner
        learn.metrics = self
        
    def before_epoch(self, learn):
        # Reset metrics
        [o.reset() for o in self.all_metrics.values()]
        
    def after_epoch(self, learn):
        # Print summary of metrics
        log = {k: f'{v.compute():.3f}' for k, v in self.all_metrics.items()}
        log['epoch'] = learn.epoch
        log['train'] = 'train' if learn.model.training else 'eval'
        # Trigger printing of the metrics
        self._log(log)
        
    def after_batch(self, learn):
        # Update metrics
        # put x, and y onto cpu
        x, y, *_  = to_cpu(learn.batch)
        # put preds onto cpu and calculate metric for each metric
        for m in self.metrics.values():
            m.update(to_cpu(learn.preds), y)
        # update the loss (Note that loss has been instantiated from the Mean class where the weight is used)
        self.loss.update(to_cpu(learn.loss), weight=len(x))
        

# %% ../nbs/09_Learner.ipynb 50
class Learner():
    def __init__(self, model, dls, loss_func=F.mse_loss, lr=0.1, cbs=None, opt_func=optim.SGD):
        cbs = fc.L(cbs)
        fc.store_attr() 
        
    @contextmanager
    def cb_ctx(self, nm):
        try:
            self.callback(f'before_{nm}')
            yield
            self.callback(f'after_{nm}')
        except globals()[f'Cancel{nm.title()}Exception']: pass
        finally: self.callback(f'cleanup_{nm}')
                                 
    def one_epoch(self, train):
        self.model.train(train)
        self.dl = self.dls.train if train else self.dls.valid
        with self.cb_ctx('epoch'):
            for self.iter,self.batch in enumerate(self.dl):
                with self.cb_ctx('batch'):
                    self.predict()
                    self.get_loss()
                    if self.training:
                        self.backward()
                        self.step()
                        self.zero_grad()
            
    
    def fit(self, n_epochs=1, train=True, valid=True, cbs=None, lr=None):
        """ train and evaluate model over n_epochs.  To do so:
        Create optimizer
        Send the model to the correct device
        Iterate through each epoch for train and then eval
        """
        cbs = fc.L(cbs)
        for cb in cbs: self.cbs.append(cb)
        try:
            self.n_epochs = n_epochs
            self.epochs = range(n_epochs)
            self.opt = self.opt_func(self.model.parameters(), self.lr if lr is None else lr)
            with self.cb_ctx('fit'):
                for self.epoch in self.epochs:
                    if train: self.one_epoch(train=True)
                    if valid:
                        with torch.no_grad():
                            self.one_epoch(train=False)
        finally:
            for cb in cbs: self.cbs.remove(cb)
                
    def __getattr__(self, name):
        """ by setting this up the functions named below become additional callbacks
        """
        if name in ('predict', 'get_loss', 'backward', 'step', 'zero_grad'):
            return partial(self.callback, name)
        raise AttributeError(name)
    
    def callback(self, method_nm):
        run_cbs(self.cbs, method_nm, self)
        
    @property
    def training(self): return self.model.training
    

# %% ../nbs/09_Learner.ipynb 52
class ProgressCB(Callback):
    """ Need to make sure that this callback is higher in the order than the metrics callback so that results 
    are updated.
    
    The progress callbar will both plot a bar of the progress through the epochs and also a sub bar of 
    progress through the batches of an epoch
    
    It also outputs a summary of loss and updates the plot after each batch
    
    """
    order = MetricsCB.order + 1
    
    def __init__(self, plot=False): self.plot=plot
        
    def before_fit(self, learn):
        # Replace epochs with the master bar to enable plotting progress
        learn.epochs = self.mbar = master_bar(learn.epochs)
        # Replace teh learner metrics log with the log from this class
        self.first = True
        if hasattr(learn, 'metrics'): learn.metrics._log = self._log
        self.losses = []
        
    def _log(self, d):
        """ Write the metrics and loss to the output
        """
        if self.first:
            self.mbar.write(list(d), table=True)
            self.first=False
        self.mbar.write(list(d.values()), table=True)
    
    def before_epoch(self, learn):
        """ Setup the second progress bar for the batches
        """
        learn.dl = progress_bar(learn.dl, leave=False, parent=self.mbar)
    
    def after_batch(self, learn):
        learn.dl.comment = f"{learn.loss:.3f}"
        if self.plot and hasattr(learn, 'metrics') and learn.training:
            self.losses.append(learn.loss.item())
            # when a collection or list is passed to fc.L.range it returns a range that is based upon the 
            # length of the collection
            self.mbar.update_graph([[fc.L.range(self.losses), self.losses]])

# %% ../nbs/09_Learner.ipynb 53
class TrainCB(Callback):
    def __init__(self, n_inp=1): self.n_inp = n_inp
    def predict(self, learn): learn.preds = learn.model(*learn.batch[:self.n_inp])
    def get_loss(self, learn): learn.loss = learn.loss_func(learn.preds, *learn.batch[self.n_inp:])
    def backward(self, learn): learn.loss.backward()
    def step(self, learn): learn.opt.step()
    def zero_grad(self, learn): learn.opt.zero_grad()

# %% ../nbs/09_Learner.ipynb 62
class with_cbs():
    def __init__(self, nm):
        self.nm = nm
    def __call__(self, f):
        def _f(o, *args, **kwargs):
            try:
                o.callback(f'before_{self.nm}')
                f(o, *args, **kwargs)
                o.callback(f'after_{self.nm}')
            except globals()[f'Cancel{self.nm.title()}Exception']: pass
            finally: o.callback(f'cleanup_{self.nm}')
        return _f

# %% ../nbs/09_Learner.ipynb 63
class Learner():
    def __init__(self, model, dls=(0,), loss_func=F.mse_loss, lr=0.1, cbs=None, opt_func=optim.SGD):
        cbs = fc.L(cbs)
        fc.store_attr()
        
    @with_cbs('batch')
    def _one_batch(self):
        self.predict()
        self.callback('after_predict')
        self.get_loss()
        self.callback('after_loss')
        if self.training:
            self.backward()
            self.callback('after_backward')
            self.step()
            self.callback('after_step')
            self.zero_grad()
            
    @with_cbs('epoch')
    def _one_epoch(self):
        for self.iter, self.batch in enumerate(self.dl): self._one_batch()
        
    def one_epoch(self, training):
        self.model.train(training)
        self.dl = self.dls.train if training else self.dls.valid
        self._one_epoch()
        
    @with_cbs('fit')
    def _fit(self, train, valid):
        for self.epoch in self.epochs:
            if train: self.one_epoch(True)
            if valid: torch.no_grad()(self.one_epoch)(False)
    
    def fit(self, n_epochs=1, train=True, valid=True, cbs=None, lr=None):
        cbs = fc.L(cbs)
        for cb in cbs: self.cbs.append(cb)
        try:
            self.n_epochs=n_epochs
            self.epochs = range(n_epochs)
            if lr is None: lr=self.lr
            if self.opt_func: self.opt = self.opt_func(self.model.parameters(), lr)
            self._fit(train, valid)
        finally:
            for cb in cbs: self.cbs.remove(cb)
    
    def __getattr__(self, name):
        if name in ('predict','get_loss','backward','step','zero_grad'): return partial(self.callback, name)
        raise AttributeError(name)
        
    def callback(self, method_nm): run_cbs(self.cbs, method_nm, self)
    
    @property
    def training(self): return self.model.training
            
            

# %% ../nbs/09_Learner.ipynb 68
class TrainLearner(Learner):
    def predict(self): self.preds = self.model(self.batch[0])
    def get_loss(self): self.loss = self.loss_func(self.preds, self.batch[1])
    def backward(self): self.loss.backward()
    def step(self): self.opt.step()
    def zero_grad(self): self.opt.zero_grad()

# %% ../nbs/09_Learner.ipynb 69
class MomentumLearner(TrainLearner):
    def __init__(self, model, dls, loss_func, lr=None, cbs=None, opt_func=optim.SGD, mom=0.85):
        self.mom=mom
        super().__init__(model, dls, loss_func, lr, cbs, opt_func)

    def zero_grad(self):
        with torch.no_grad():
            for p in self.model.parameters(): p.grad *= self.mom

# %% ../nbs/09_Learner.ipynb 76
from torch.optim.lr_scheduler import ExponentialLR

# %% ../nbs/09_Learner.ipynb 77
class LRFinderCB(Callback):
    def __init__(self, gamma=1.3, max_mult=3): fc.store_attr()
    
    def before_fit(self, learn):
        self.losses, self.lrs = [], []
        self.sched = ExponentialLR(learn.opt, gamma=self.gamma)
        self.min = math.inf
        
    def after_batch(self, learn):
        # add lr and loss to lists
        # update plot
        # check whether to continue, if so
        # update lr, 
        if not learn.model.training: raise CancelEpochException()
        self.lrs.append(learn.opt.param_groups[0]['lr'])
        loss = to_cpu(learn.loss)
        self.losses.append(loss)
        if loss < self.min: self.min=loss
        # test of starting to become unstable
        if loss > self.min * self.max_mult: raise CancelFitException()
        # update the learning rates in the param_groups
        self.sched.step()
        
    def cleanup_fit(self, learn):
        plt.plot(self.lrs, self.losses)
        plt.xscale('log')

# %% ../nbs/09_Learner.ipynb 79
@fc.patch
def lr_find(self:Learner, gamma=1.3, max_mult=3, start_lr=1e-5, max_epochs=10):
    self.fit(max_epochs, lr=start_lr, cbs=LRFinderCB(gamma=gamma, max_mult=max_mult))
