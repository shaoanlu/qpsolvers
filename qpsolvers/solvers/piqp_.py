#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2022 Stéphane Caron and the qpsolvers contributors.
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

"""Solver interface for `PIQP`_.

.. _PIQP: https://github.com/PREDICT-EPFL/piqp

PIQP is a Proximal Interior Point Quadratic Programming solver, which can
solve dense and sparse quadratic programs. Combining an infeasible interior
point method with the proximal method of multipliers, the algorithm can
handle ill-conditioned convex QP problems without the need for linear
independence of the constraints.
"""

import warnings
from typing import Optional, Union

import numpy as np
import piqp
import scipy.sparse as spa

from ..conversions import ensure_sparse_matrices
from ..exceptions import ParamError, ProblemError
from ..problem import Problem
from ..solution import Solution


def __select_backend(backend: Optional[str], use_csc: bool):
    """Select backend function for PIQP.

    Parameters
    ----------
    backend :
        PIQP backend to use in ``[None, "dense", "sparse"]``. If ``None``
        (default), the backend is selected based on the type of ``P``.
    use_csc :
        If ``True``, use sparse matrices if the backend is not specified.

    Returns
    -------
    :
        Backend solve function.

    Raises
    ------
    ParamError
        If the required backend is not a valid PIQP backend.
    """
    if backend is None:
        return piqp.SparseSolver() if use_csc else piqp.DenseSolver()
    if backend == "dense":
        return piqp.DenseSolver()
    if backend == "sparse":
        return piqp.SparseSolver()
    raise ParamError(f'Unknown PIQP backend "{backend}')


def piqp_solve_problem(
    problem: Problem,
    initvals: Optional[np.ndarray] = None,
    verbose: bool = False,
    backend: Optional[str] = None,
    **kwargs,
) -> Solution:
    """Solve a quadratic program using PIQP.

    Parameters
    ----------
    problem :
        Quadratic program to solve.
    initvals :
        Warm-start guess vector (not used).
    backend :
        PIQP backend to use in ``[None, "dense", "sparse"]``. If ``None``
        (default), the backend is selected based on the type of ``P``.
    verbose :
        Set to `True` to print out extra information.

    Returns
    -------
    :
        Solution to the QP returned by the solver.

    Notes
    -----
    All other keyword arguments are forwarded as options to PIQP. For
    instance, you can call ``piqp_solve_qp(P, q, G, h, eps_abs=1e-6)``.
    For a quick overview, the solver accepts the following settings:

    .. list-table::
       :widths: 30 70
       :header-rows: 1

       * - Name
         - Effect
       * - ``rho_init``
         - Initial value for the primal proximal penalty parameter rho.
       * - ``delta_init``
         - Initial value for the augmented lagrangian penalty parameter delta.
       * - ``eps_abs``
         - Absolute tolerance.
       * - ``eps_rel``
         - Relative tolerance.
       * - ``check_duality_gap``
         - Check terminal criterion on duality gap.
       * - ``eps_duality_gap_abs``
         - Absolute tolerance on duality gap.
       * - ``eps_duality_gap_rel``
         - Relative tolerance on duality gap.
       * - ``reg_lower_limit``
         - Lower limit for regularization.
       * - ``reg_finetune_lower_limit``
         - Fine tune lower limit regularization.
       * - ``reg_finetune_primal_update_threshold``
         - Threshold of number of no primal updates to transition to fine
           tune mode.
       * - ``reg_finetune_dual_update_threshold``
         - Threshold of number of no dual updates to transition to fine
           tune mode.
       * - ``max_iter``
         - Maximum number of iterations.
       * - ``max_factor_retires``
         - Maximum number of factorization retires before failure.
       * - ``preconditioner_scale_cost``
         - 	Scale cost in Ruiz preconditioner.
       * - ``preconditioner_iter``
         - Maximum of preconditioner iterations.
       * - ``tau``
         - Maximum interior point step length.
       * - ``iterative_refinement_always_enabled``
         - Always run iterative refinement and not only on factorization
           failure.
       * - ``iterative_refinement_eps_abs``
         - Iterative refinement absolute tolerance.
       * - ``iterative_refinement_eps_rel``
         - Iterative refinement relative tolerance.
       * - ``iterative_refinement_max_iter``
         - Maximum number of iterations for iterative refinement.
       * - ``iterative_refinement_min_improvement_rate``
         - Minimum improvement rate for iterative refinement.
       * - ``iterative_refinement_static_regularization_eps``
         - Static regularization for KKT system for iterative refinement.
       * - ``iterative_refinement_static_regularization_rel``
         - Static regularization w.r.t. the maximum abs diagonal term of
           KKT system.
       * - ``verbose``
         - Verbose printing.
       * - ``compute_timings``
         - Measure timing information internally.

    This list is not exhaustive. Check out the `solver documentation
    <https://predict-epfl.github.io/piqp/interfaces/settings>`__ for details.
    """
    P, q, G, h, A, b, lb, ub = problem.unpack()
    n: int = q.shape[0]

    if initvals is not None and verbose:
        warnings.warn("warm-start values are ignored by PIQP")

    if G is None and h is not None:
        raise ProblemError(
            "Inconsistent inequalities: G is not set but h is set"
        )
    if G is not None and h is None:
        raise ProblemError("Inconsistent inequalities: G is set but h is None")
    if A is None and b is not None:
        raise ProblemError(
            "Inconsistent inequalities: A is not set but b is set"
        )
    if A is not None and b is None:
        raise ProblemError("Inconsistent inequalities: A is set but b is None")
    use_csc: bool = (
        not isinstance(P, np.ndarray)
        or (G is not None and not isinstance(G, np.ndarray))
        or (A is not None and not isinstance(A, np.ndarray))
    )
    if use_csc is True:
        P, G, A = ensure_sparse_matrices(P, G, A)
    # PIQP does not accept A, b, G, and H as None.
    G_piqp = np.zeros((1, n)) if G is None else G
    h_piqp = np.zeros((1,)) if h is None else h
    A_piqp = np.zeros((1, n)) if A is None else A
    b_piqp = np.zeros((1,)) if b is None else b

    solver = __select_backend(backend, use_csc)
    solver.settings.verbose = verbose
    for key, value in kwargs.items():
        try:
            setattr(solver.settings, key, value)
        except AttributeError:
            if verbose:
                warnings.warn(
                    f"Received an undefined solver setting {key}\
                    with value {value}"
                )
    solver.setup(P, q, A_piqp, b_piqp, G_piqp, h_piqp, lb, ub)
    status = solver.solve()
    success_status = piqp.PIQP_SOLVED

    solution = Solution(problem)
    solution.extras = {"info": solver.result.info}
    solution.found = status == success_status
    solution.x = solver.result.x
    if A is None:
        solution.y = solver.result.y
    else:
        solution.y = np.empty((0,))
    if G is not None:
        solution.z = np.empty((0,))
        solution.z_box = np.empty((0,))
    else:
        solution.z = solver.result.z
        solution.z_box = solver.result.z_ub - solver.result.z_lb
    return solution


def piqp_solve_qp(
    P: Union[np.ndarray, spa.csc_matrix],
    q: Union[np.ndarray, spa.csc_matrix],
    G: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    h: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    A: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    b: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    lb: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    ub: Optional[Union[np.ndarray, spa.csc_matrix]] = None,
    initvals: Optional[np.ndarray] = None,
    verbose: bool = False,
    backend: Optional[str] = None,
    **kwargs,
) -> Optional[np.ndarray]:
    r"""Solve a quadratic program using PIQP.

    The quadratic program is defined as:

    .. math::

        \begin{split}\begin{array}{ll}
        \underset{\mbox{minimize}}{x} &
            \frac{1}{2} x^T P x + q^T x \\
        \mbox{subject to}
            & G x \leq h                \\
            & A x = b                   \\
            & lb \leq x \leq ub
        \end{array}\end{split}

    It is solved using `PIQP
    <https://github.com/PREDICT-EPFL/piqp>`__.

    Parameters
    ----------
    P :
        Positive semidefinite cost matrix.
    q :
        Cost vector.
    G :
        Linear inequality constraint matrix.
    h :
        Linear inequality constraint vector.
    A :
        Linear equality constraint matrix.
    b :
        Linear equality constraint vector.
    lb :
        Lower bound constraint vector.
    ub :
        Upper bound constraint vector.
    backend :
        PIQP backend to use in ``[None, "dense", "sparse"]``. If ``None``
        (default), the backend is selected based on the type of ``P``.
    verbose :
        Set to `True` to print out extra information.
    initvals :
        Warm-start guess vector. Not used.

    Returns
    -------
    :
        Primal solution to the QP, if found, otherwise ``None``.
    """
    problem = Problem(P, q, G, h, A, b, lb, ub)
    solution = piqp_solve_problem(
        problem, initvals, verbose, backend, **kwargs
    )
    return solution.x if solution.found else None
