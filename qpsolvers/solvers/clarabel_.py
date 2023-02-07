#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 Inria
#
# This file is part of qpsolvers.
#
# qpsolvers is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# qpsolvers is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with qpsolvers. If not, see <http://www.gnu.org/licenses/>.

"""Solver interface for `Clarabel.rs`_.

.. _Clarabel.rs: https://github.com/oxfordcontrol/Clarabel.rs

Clarabel.rs is a Rust implementation of an interior point numerical solver for
convex optimization problems using a novel homogeneous embedding. A paper
describing the Clarabel solver algorithm and implementation will be forthcoming
soon (retrieved: 2023-02-06). Until then, the authors ask that you cite its
documentation if you have found Clarabel.rs useful in your work.
"""

import warnings
from typing import Optional, Union

import clarabel
import numpy as np
import scipy.sparse as spa

from ..conversions import (
    ensure_sparse_matrices,
    linear_from_box_inequalities,
    split_dual_linear_box,
)
from ..problem import Problem
from ..solution import Solution


def clarabel_solve_problem(
    problem: Problem,
    initvals: Optional[np.ndarray] = None,
    verbose: bool = False,
    **kwargs,
) -> Solution:
    r"""Solve a quadratic program using Clarabel.rs.

    Parameters
    ----------
    problem :
        Quadratic program to solve.
    initvals :
        Warm-start guess vector.
    verbose :
        Set to `True` to print out extra information.

    Returns
    -------
    :
        Solution to the QP, if found, otherwise ``None``.

    Notes
    -----
    Keyword arguments are forwarded as options to Clarabel.rs. For instance, we
    can call ``clarabel_solve_qp(P, q, G, h, u, ...........)``.
    Clarabel options include the following:

    .. list-table::
       :widths: 30 70
       :header-rows: 1

       * - Name
         - Description
       * - ``max_iter``
         - Maximum number of iterations.
       * - ``time_limit``
         - Time limit for solve run in seconds (can be fractional).

    Check out the `Rust API reference
    <https://docs.rs/clarabel/latest/clarabel/>`_ for details.
    """
    P, q, G, h, A, b, lb, ub = problem.unpack()
    P, G, A = ensure_sparse_matrices(P, G, A)
    if lb is not None or ub is not None:
        G, h = linear_from_box_inequalities(G, h, lb, ub, use_sparse=True)

    cones = []
    A_list = []
    b_list = []
    if A is not None and b is not None:
        A_list.append(A)
        b_list.append(b)
        cones.append(clarabel.ZeroConeT(b.shape[0]))
    if G is not None and h is not None:
        A_list.append(G)
        b_list.append(h)
        cones.append(clarabel.NonnegativeConeT(h.shape[0]))

    settings = clarabel.DefaultSettings()
    settings.verbose = verbose
    for key, value in kwargs.items():
        settings.__setattr__(key, value)

    A_stack = spa.vstack(A_list, format="csc")
    b_stack = np.concatenate(b_list)
    solver = clarabel.DefaultSolver(P, q, A_stack, b_stack, cones, settings)
    result = solver.solve()

    solution = Solution(problem)
    solution.extras = {
        "status": result.status,
        "solve_time": result.solve_time,
    }

    # Disabled for now
    # See https://github.com/oxfordcontrol/Clarabel.rs/issues/10
    if False and result.status != clarabel.SolverStatus.Solved:
        warnings.warn(f"Clarabel.rs terminated with status {result.status}")
        return solution

    solution.x = np.array(result.x)
    meq = A.shape[0] if A is not None else 0
    if meq > 0:
        solution.y = result.z[:meq]
    if G is not None:
        z, z_box = split_dual_linear_box(np.array(result.z[meq:]), lb, ub)
        solution.z = z
        solution.z_box = z_box
    return solution


def clarabel_solve_qp(
    P: Union[np.ndarray, spa.csc_matrix],
    q: np.ndarray,
    G: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    h: Optional[np.ndarray] = None,
    A: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    b: Optional[np.ndarray] = None,
    lb: Optional[np.ndarray] = None,
    ub: Optional[np.ndarray] = None,
    solver: Optional[str] = None,
    initvals: Optional[np.ndarray] = None,
    verbose: bool = False,
    **kwargs,
) -> Optional[np.ndarray]:
    r"""Solve a quadratic program using Clarabel.rs.

    The quadratic program is defined as:

    .. math::

        \begin{split}\begin{array}{ll}
            \underset{x}{\mbox{minimize}} &
                \frac{1}{2} x^T P x + q^T x \\
            \mbox{subject to}
                & G x \leq h                \\
                & A x = b                   \\
                & lb \leq x \leq ub
        \end{array}\end{split}

    It is solved using `Clarabel.rs`_.

    Parameters
    ----------
    P :
        Symmetric cost matrix.
    q :
        Cost vector.
    G :
        Linear inequality matrix.
    h :
        Linear inequality vector.
    A :
        Linear equality constraint matrix.
    b :
        Linear equality constraint vector.
    lb :
        Lower bound constraint vector.
    ub :
        Upper bound constraint vector.
    initvals :
        Warm-start guess vector.
    verbose :
        Set to `True` to print out extra information.

    Returns
    -------
    :
        Primal solution to the QP, if found, otherwise ``None``.
    """
    problem = Problem(P, q, G, h, A, b, lb, ub)
    solution = clarabel_solve_problem(problem, initvals, verbose, **kwargs)
    return solution.x