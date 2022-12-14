# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/11_initializing.ipynb.

# %% auto 0
__all__ = ['clean_ipython_hist', 'clean_tb', 'clean_mem', 'BatchTransformCB', 'GeneralRelu', 'plot_func', 'init_weights',
           'lsuv_init', 'conv', 'get_model']

# %% ../nbs/11_initializing.ipynb 2
import pickle,gzip,math,os,time,shutil,torch,matplotlib as mpl,numpy as np,matplotlib.pyplot as plt
import sys,gc,traceback
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
from torcheval.metrics import MulticlassAccuracy
from datasets import load_dataset,load_dataset_builder

from .datasets import *
from .conv import *
from .learner import *
from .activations import *

# %% ../nbs/11_initializing.ipynb 15
def clean_ipython_hist():
    # Code in this function mainly copied from IPython source
    if not 'get_ipython' in globals(): return
    ip = get_ipython()
    user_ns = ip.user_ns
    ip.displayhook.flush()
    pc = ip.displayhook.prompt_count + 1
    for n in range(1, pc): user_ns.pop('_i'+repr(n),None)
    user_ns.update(dict(_i='',_ii='',_iii=''))
    hm = ip.history_manager
    hm.input_hist_parsed[:] = [''] * pc
    hm.input_hist_raw[:] = [''] * pc
    hm._i = hm._ii = hm._iii = hm._i00 =  ''

# %% ../nbs/11_initializing.ipynb 16
def clean_tb():
    # h/t Piotr Czapla
    if hasattr(sys, 'last_traceback'):
        traceback.clear_frames(sys.last_traceback)
        delattr(sys, 'last_traceback')
    if hasattr(sys, 'last_type'): delattr(sys, 'last_type')
    if hasattr(sys, 'last_value'): delattr(sys, 'last_value')

# %% ../nbs/11_initializing.ipynb 17
def clean_mem():
    clean_tb()
    clean_ipython_hist()
    gc.collect()
    torch.cuda.empty_cache()

# %% ../nbs/11_initializing.ipynb 89
class BatchTransformCB(Callback):
    def __init__(self, tfm, on_train=True, on_val=True): fc.store_attr()
    
    def before_batch(self, learn):
        if (self.on_train and learn.training) or (self.on_val and not learn.training): 
            learn.batch = self.tfm(learn.batch)

# %% ../nbs/11_initializing.ipynb 101
class GeneralRelu(nn.Module):
    def __init__(self, leak=None, sub=None, maxv=None):
        super().__init__()
        self.leak, self.sub, self. maxv = leak, sub, maxv
        
    def forward(self, x):
        x = F.leaky_relu(x, self.leak) if self.leak is not None else F.relu(x)
        if self.sub is not None: x -= self.sub
        if self.maxv is not None: x = x.clamp_max_(self.maxv)
        return x

# %% ../nbs/11_initializing.ipynb 102
def plot_func(f, start=-5, end=5, steps=100):
    x = torch.linspace(start, end, steps)
    plt.plot(x, f(x))
    plt.grid(visible=True, which='both', ls='--')
    plt.axhline(y=0, color='k', linewidth=1.0)
    plt.axvline(x=0, color='k', linewidth=1.0)

# %% ../nbs/11_initializing.ipynb 107
def init_weights(m, leaky=0.):
    if isinstance(m, (nn.Conv1d,nn.Conv2d,nn.Conv3d)): init.kaiming_normal_(m.weight, a=leaky)

# %% ../nbs/11_initializing.ipynb 116
def _lsuv_stats(hook, mod, inp, outp):
    """Calculate stats for a specific module given the input and output values.  Assigns the mean and std
    as properties of the hook
    """
    acts = to_cpu(outp)
    hook.mean = acts.mean()
    hook.std = acts.std()
    
def lsuv_init(m, m_in, xb):
    """ Setput hook for specific module (one of the activation layer outputs usually).  Run a batch of 
    data trhough the model and adjust the weights of the layer feeding the hooked layer to bring the mean
    and std deviation at the end of thta layer to the target values
    
    args:
        m: layer to apply hook to.  Usually the output of an activation
        m_in: layer prior to the activation
        xb: a batch of data
    """
    h = Hook(m, _lsuv_stats)
    with torch.no_grad():
        while model(xb) is not None and (abs(h.mean)>1e-3 or (abs(h.std-1)>1.e-3)):
            m_in.bias -= h.mean
            m_in.weight.data /= h.std
    h.remove()
    

# %% ../nbs/11_initializing.ipynb 130
def conv(ni, nf, ks=3, stride=2, act=nn.ReLU, norm=None, bias=None):
    if bias is None:
        bias = not isinstance(norm, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d))
    layers = [nn.Conv2d(ni, nf, stride=stride, kernel_size=ks, padding=ks//2, bias=bias)]
    if norm: layers.append(norm(nf))
    if act: layers.append(act())
    return nn.Sequential(*layers)

# %% ../nbs/11_initializing.ipynb 131
def get_model(act=nn.ReLU, nfs=None, norm=None):
    if nfs==None: nfs=[1, 8, 16, 32, 64]
    layers = [conv(nfs[o], nfs[o+1], act=act, norm=norm) for o in range(len(nfs)-1)]
    return nn.Sequential(*layers, conv(nfs[-1], 10, ks=3, norm=False, act=None, bias=True),
                        nn.Flatten()).to(def_device)
