# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/13_resnet-Copy1.ipynb.

# %% auto 0
__all__ = ['act_gr', 'ResBlock']

# %% ../nbs/13_resnet-Copy1.ipynb 2
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
from .sgd import *

# %% ../nbs/13_resnet-Copy1.ipynb 5
act_gr = partial(GeneralRelu, leak=0.1, sub=0.4)

# %% ../nbs/13_resnet-Copy1.ipynb 16
def _conv_block(ni, nf, stride, ks=3, act=act_gr, norm=None):
    """ Note that the architectual choice being made here is that the first conv does the re-scaling
    and the second keeps the number of channels the same but reduces the resolution by using stride=2
    
    The pass through block uses a pooling layer to reduce the resolution and then a basic conv to change
    the number of channels to that required
    
    """
    return nn.Sequential(
        conv(ni, nf, stride=1, ks=3, act=act, norm=norm),
        conv(nf, nf, stride=stride, ks=3, act=None, norm=norm)
    )

class ResBlock(nn.Module):
    def __init__(self, ni, nf, stride=1, ks=3, act=act_gr, norm=None):
        super().__init__()
        # Create the two convolution layers
        self.convs = _conv_block(ni, nf, stride, ks=ks, act=act, norm=norm)
        # Create the pass through layer.  Note that this can only be a complete pass of the input if ni=nf.
        # Where this is not the case a single conv is used (with no activation and kernel size of 1)
        self.idconv = fc.noop if ni==nf else conv(ni, nf, stride=1, ks=1, act=None)
        self.pool = fc.noop if stride==1 else nn.AvgPool2d(kernel_size=2, ceil_mode=True)
        self.act = act()
        
    def forward(self, x):
        return self.act(self.convs(x)) + self.idconv(self.pool(x))
    
