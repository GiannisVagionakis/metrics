# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import List, Optional, Sequence, Tuple, Union

import torch
from torch import Tensor

from torchmetrics.functional.classification.precision_recall_curve import (
    _binary_clf_curve,
    _precision_recall_curve_update,
)


def _roc_update(
    preds: Tensor,
    target: Tensor,
    num_classes: Optional[int] = None,
    pos_label: Optional[int] = None,
) -> Tuple[Tensor, Tensor, int, int, str]:
    preds, target, num_classes, pos_label = _precision_recall_curve_update(preds, target, num_classes, pos_label)
    return preds, target, num_classes, pos_label


def _roc_compute(
    preds: Tensor,
    target: Tensor,
    num_classes: int,
    pos_label: int,
    sample_weights: Optional[Sequence] = None,
) -> Union[Tuple[Tensor, Tensor, Tensor], Tuple[List[Tensor], List[Tensor], List[Tensor]]]:
    with torch.no_grad():
        if num_classes == 1 and preds.ndim == 1:  # binary
            fps, tps, thresholds = _binary_clf_curve(
                preds=preds, target=target, sample_weights=sample_weights, pos_label=pos_label
            )
            # Add an extra threshold position
            # to make sure that the curve starts at (0, 0)
            tps = torch.cat([torch.zeros(1, dtype=tps.dtype, device=tps.device), tps])
            fps = torch.cat([torch.zeros(1, dtype=fps.dtype, device=fps.device), fps])
            thresholds = torch.cat([thresholds[0][None] + 1, thresholds])

            if fps[-1] <= 0:
                raise ValueError("No negative samples in targets, false positive value should be meaningless")
            fpr = fps / fps[-1]

            if tps[-1] <= 0:
                raise ValueError("No positive samples in targets, true positive value should be meaningless")
            tpr = tps / tps[-1]

            return fpr, tpr, thresholds

        # Recursively call per class
        fpr, tpr, thresholds = [], [], []
        for c in range(num_classes):
            if preds.shape == target.shape:
                preds_c = preds[:, c]
                target_c = target[:, c]
                pos_label = 1
            else:
                preds_c = preds[:, c]
                target_c = target
                pos_label = c
            res = roc(
                preds=preds_c,
                target=target_c,
                num_classes=1,
                pos_label=pos_label,
                sample_weights=sample_weights,
            )
            fpr.append(res[0])
            tpr.append(res[1])
            thresholds.append(res[2])

        return fpr, tpr, thresholds


def roc(
    preds: Tensor,
    target: Tensor,
    num_classes: Optional[int] = None,
    pos_label: Optional[int] = None,
    sample_weights: Optional[Sequence] = None,
) -> Union[Tuple[Tensor, Tensor, Tensor], Tuple[List[Tensor], List[Tensor], List[Tensor]]]:
    """
    Computes the Receiver Operating Characteristic (ROC).
    Works with both binary, multiclass and multilabel input.

    Args:
        preds: predictions from model (logits or probabilities)
        target: ground truth values
        num_classes: integer with number of classes for multi-label and multiclass problems.
            Should be set to ``None`` for binary problems
        pos_label: integer determining the positive class. Default is ``None``
            which for binary problem is translate to 1. For multiclass problems
            this argument should not be set as we iteratively change it in the
            range [0,num_classes-1]
        sample_weights: sample weights for each data point

    Returns:
        3-element tuple containing

        fpr:
            tensor with false positive rates.
            If multiclass or multilabel, this is a list of such tensors, one for each class/label.
        tpr:
            tensor with true positive rates.
            If multiclass or multilabel, this is a list of such tensors, one for each class/label.
        thresholds:
            tensor with thresholds used for computing false- and true postive rates
            If multiclass or multilabel, this is a list of such tensors, one for each class/label.

    Example (binary case):
        >>> from torchmetrics.functional import roc
        >>> pred = torch.tensor([0, 1, 2, 3])
        >>> target = torch.tensor([0, 1, 1, 1])
        >>> fpr, tpr, thresholds = roc(pred, target, pos_label=1)
        >>> fpr
        tensor([0., 0., 0., 0., 1.])
        >>> tpr
        tensor([0.0000, 0.3333, 0.6667, 1.0000, 1.0000])
        >>> thresholds
        tensor([4, 3, 2, 1, 0])

    Example (multiclass case):
        >>> from torchmetrics.functional import roc
        >>> pred = torch.tensor([[0.75, 0.05, 0.05, 0.05],
        ...                      [0.05, 0.75, 0.05, 0.05],
        ...                      [0.05, 0.05, 0.75, 0.05],
        ...                      [0.05, 0.05, 0.05, 0.75]])
        >>> target = torch.tensor([0, 1, 3, 2])
        >>> fpr, tpr, thresholds = roc(pred, target, num_classes=4)
        >>> fpr
        [tensor([0., 0., 1.]), tensor([0., 0., 1.]), tensor([0.0000, 0.3333, 1.0000]), tensor([0.0000, 0.3333, 1.0000])]
        >>> tpr
        [tensor([0., 1., 1.]), tensor([0., 1., 1.]), tensor([0., 0., 1.]), tensor([0., 0., 1.])]
        >>> thresholds # doctest: +NORMALIZE_WHITESPACE
        [tensor([1.7500, 0.7500, 0.0500]),
         tensor([1.7500, 0.7500, 0.0500]),
         tensor([1.7500, 0.7500, 0.0500]),
         tensor([1.7500, 0.7500, 0.0500])]

    Example (multilabel case):
        >>> from torchmetrics.functional import roc
        >>> pred = torch.tensor([[0.8191, 0.3680, 0.1138],
        ...                      [0.3584, 0.7576, 0.1183],
        ...                      [0.2286, 0.3468, 0.1338],
        ...                      [0.8603, 0.0745, 0.1837]])
        >>> target = torch.tensor([[1, 1, 0], [0, 1, 0], [0, 0, 0], [0, 1, 1]])
        >>> fpr, tpr, thresholds = roc(pred, target, num_classes=3, pos_label=1)
        >>> fpr # doctest: +NORMALIZE_WHITESPACE
        [tensor([0.0000, 0.3333, 0.3333, 0.6667, 1.0000]),
         tensor([0., 0., 0., 1., 1.]),
         tensor([0.0000, 0.0000, 0.3333, 0.6667, 1.0000])]
        >>> tpr
        [tensor([0., 0., 1., 1., 1.]), tensor([0.0000, 0.3333, 0.6667, 0.6667, 1.0000]), tensor([0., 1., 1., 1., 1.])]
        >>> thresholds # doctest: +NORMALIZE_WHITESPACE
        [tensor([1.8603, 0.8603, 0.8191, 0.3584, 0.2286]),
         tensor([1.7576, 0.7576, 0.3680, 0.3468, 0.0745]),
         tensor([1.1837, 0.1837, 0.1338, 0.1183, 0.1138])]

    """
    preds, target, num_classes, pos_label = _roc_update(preds, target, num_classes, pos_label)
    return _roc_compute(preds, target, num_classes, pos_label, sample_weights)
