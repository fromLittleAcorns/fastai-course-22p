# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/14_augment-Copy1.ipynb.

# %% auto 0
__all__ = []

# %% ../nbs/14_augment-Copy1.ipynb 2
import pickle,gzip,math,os,time,shutil,torch,random
import fastcore.all as fc,matplotlib as mpl,numpy as np,matplotlib.pyplot as plt
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
from .resnet import *
