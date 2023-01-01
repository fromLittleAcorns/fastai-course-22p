# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/12_accel_sgd.ipynb.

# %% auto 0
__all__ = ['BaseSchedCB', 'BatchSchedCB', 'HasLearnCB', 'RecorderCB', 'EpochSchedCB']

# %% ../nbs/12_accel_sgd.ipynb 2
import pickle,gzip,math,os,time,shutil,torch,matplotlib as mpl,numpy as np,matplotlib.pyplot as plt
import fastcore.all as fc
from collections.abc import Mapping
from pathlib import Path
from operator import attrgetter,itemgetter
from functools import partial
from copy import copy
from contextlib import contextmanager

import torchvision.transforms.functional as TF,torch.nn.functional as F
from torch import tensor,nn,optim
from torch.utils.data import DataLoader,default_collate
from torch.nn import init
from torch.optim import lr_scheduler
from torcheval.metrics import MulticlassAccuracy
from datasets import load_dataset,load_dataset_builder

from .datasets import *
from .conv import *
from .learner import *
from .activations import *
from .init import *

# %% ../nbs/12_accel_sgd.ipynb 48
class BaseSchedCB(Callback):
    """ define the scheduler to use and assign the optimiser.  Create a basic step operation for the 
    scheduler
    """
    def __init__(self, sched): self.sched = sched
    def before_fit(self, learn): self.schedo = self.sched(learn.opt)
    def _step(self, learn):
        if learn.training: self.schedo.step()

# %% ../nbs/12_accel_sgd.ipynb 49
class BatchSchedCB(BaseSchedCB):
    """ step the scheduler after the batch
    """
    def after_batch(self, learn): self._step(learn)

# %% ../nbs/12_accel_sgd.ipynb 50
class HasLearnCB(Callback):
    def before_fit(self, learn): self.learn = learn 
    def after_fit(self, learn): self.learn = None

# %% ../nbs/12_accel_sgd.ipynb 51
class RecorderCB(Callback):
    """ Class to record specific keyword items during training
    """
    def __init__(self, **d): 
        self.d = d
    def before_fit(self, learn):
        self.recs = {k:[] for k in self.d}
        self.pg = learn.opt.param_groups[0]
    
    def after_batch(self, learn):
        if not learn.training: return
        for k,v in self.d.items():
            self.recs[k].append(v(self))

    def plot(self):
        for k,v in self.recs.items():
            plt.plot(v, label=k)
            plt.legend()
            plt.show()

# %% ../nbs/12_accel_sgd.ipynb 59
class EpochSchedCB(BaseSchedCB):
    def after_epoch(self, learn): self._step(learn)