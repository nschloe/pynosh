#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
Collection of numerical algorithms.
'''
# ==============================================================================
from scipy.sparse.linalg import LinearOperator
from scipy.sparse.sputils import upcast
import numpy as np
import scipy
# ==============================================================================
def l2_condition_number( linear_operator ):
    from scipy.sparse.linalg import eigs
    small_eigenval = eigs(linear_operator,
                          k = 1,
                          sigma = None,
                          which = 'SM',
                          return_eigenvectors = False
                          )
    large_eigenval = eigs(linear_operator,
                          k = 1,
                          sigma = None,
                          which = 'LM',
                          return_eigenvectors = False
                          )

    return large_eigenval[0] / small_eigenval[0]
# ==============================================================================
def _ipstd( X, Y ):
    '''Euclidean inner product
    
    np.vdot only works for vectors and np.dot does not use the conjugate
    transpose. In Octave/MATLAB notation _ipstd(X,Y) == X'*Y.

    Arguments: 
        X:  array of shape [N,m]
        Y:  array of shape [N,n]

    Returns:
        ip: array of shape [m,n] with X^H * Y
    '''
    return np.dot(X.T.conj(), Y)
# ==============================================================================
def _norm_squared( x, Mx = None, inner_product = _ipstd ):
    '''Compute the norm^2 w.r.t. to a given scalar product.'''
    assert( len(x.shape)==2 )
    assert( x.shape[1]==1 )
    if Mx is None:
        rho = inner_product(x, x)[0,0]
    else:
        assert( len(Mx.shape)==2 )
        assert( Mx.shape[1]==1 )
        rho = inner_product(x, Mx)[0,0]

#    if rho.imag != 0.0: #abs(rho.imag) > abs(rho) * 1.0e-10:
    if abs(rho.imag) > abs(rho) *1e-10:
        raise ValueError( 'M not positive definite?' )

    rho = rho.real

    if rho < 0.0:
        raise ValueError( '<x,Mx> = %g. M not positive definite?' % rho )

    return rho
# ==============================================================================
def _norm( x, Mx = None, inner_product = _ipstd ):
    '''Compute the norm w.r.t. to a given scalar product.'''
    return np.sqrt(_norm_squared( x, Mx = Mx, inner_product = inner_product ) )
# ==============================================================================
def _apply( A, x ):
    '''Implement A*x for different types of linear operators.'''
    if A is None:
        return x
    elif isinstance( A, np.ndarray ):
        return np.dot( A, x )
    elif scipy.sparse.isspmatrix(A):
        return A * x
    elif isinstance( A, scipy.sparse.linalg.LinearOperator ):
        return A * x
    else:
        raise ValueError( 'Unknown operator type "%s".' % type(A) )
# ==============================================================================
def cg(A, rhs, x0,
       tol = 1.0e-5,
       maxiter = None,
       M = None,
       explicit_residual = False,
       inner_product = _ipstd,
       exact_solution = None
       ):
    '''Conjugate gradient method with different inner product.
    '''
    xtype = upcast( A.dtype, rhs.dtype, x0.dtype )
    if M:
        xtype = upcast( xtype, M.dtype )

    x = xtype(x0.copy())
    # If len(x)==1, then xtype strips off the np.array frame around the value.
    # This is needed for _apply, though.
    if len(x0) == 1:
        x = np.array( [x] )

    r = rhs - _apply(A, x)

    Mr = _apply(M, r)
    rho_old = _norm_squared(r, Mr, inner_product = inner_product)
    p = Mr.copy()

    if maxiter is None:
        maxiter = len(rhs)

    out = {}
    out['info'] = 0

    # Store rho0 = ||rhs||_M^2.
    Mrhs = _apply(M, rhs)
    rho0 = _norm_squared( rhs, Mrhs, inner_product = inner_product )

    out['relresvec'] = np.empty(maxiter+1)
    out['relresvec'][0] = 1.0

    if exact_solution is not None:
        out['errorvec'] = np.empty(maxiter+1)
        out['errorvec'][0] = _norm_squared(x-exact_solution,
                                           inner_product = inner_product
                                           )

    k = 0
    while out['relresvec'][k] > tol and k < maxiter:
        if k > 0:
            # update the search direction
            p = Mr + rho_new/rho_old * p
            rho_old = rho_new

        Ap = _apply(A, p)

        # update current guess and residual
        alpha = rho_old / inner_product( p, Ap )
        x += alpha * p

        if exact_solution is not None:
            out['errorvec'][k+1] = _norm_squared(x-exact_solution,
                                                 inner_product = inner_product
                                                 )

        if explicit_residual:
            r = rhs - _apply(A, x)
        else:
            r -= alpha * Ap

        Mr = _apply(M, r)
        rho_new = _norm_squared( r, Mr, inner_product = inner_product )

        out['relresvec'][k+1] = np.sqrt(rho_new / rho0)
        if not explicit_residual and out['relresvec'][k+1] < tol:
            # Compute exact residual
            r = rhs - _apply(A, x)
            Mr = _apply(M, r)
            rho_new = _norm_squared( r, Mr, inner_product = inner_product )
            out['relresvec'][k+1] = np.sqrt(rho_new / rho0)

        k += 1

    if out['relresvec'][k] > tol:
        out['info'] = 1

    out['xk'] = x
    out['relresvec'] = out['relresvec'][:k+1]
    if exact_solution is not None:
        out['errorvec'] = out['errorvec'][:k+1]

    return out
# ==============================================================================
def minres(A, b, x0,
           tol = 1e-5,
           maxiter = None,
           M = None,
           Ml = None,
           Mr = None,
           inner_product = _ipstd,
           explicit_residual = False,
           return_basis = False,
           full_reortho = False,
           exact_solution = None,
           timer = False
           ):
    '''Preconditioned MINRES

    This MINRES solves M*Ml*A*Mr*y = M*Ml*b,  x=Mr*y
    where Ml and Mr have to be such that Ml*A*Mr is self-adjoint in the 
    inner_product. M has to be self-adjoint and positive-definite w.r.t.
    inner_product. 
    
    Details:
    The Lanczos procedure is used with the operator M*Ml*A*Mr and the 
    inner product defined by inner_product(M^{-1}x,y). The initial vector 
    for Lanczos is r0 = M*Ml*(b - A*x0) -- note that Mr is not used for
    the initial vector!
    
    Stopping criterion is 
    ||M*Ml*(b-A*(x0+Mr*yk))||_{M^{-1}} / ||M*Ml*b||_{M^{-1}} <= tol
    '''
    info = 0
    N = len(b)
    if maxiter is None:
        maxiter = N

    if timer:
        import time
        times = {'setup': np.empty(1),
                 'apply Ml*A*Mr': np.empty(maxiter),
                 'Lanczos': np.empty(maxiter),
                 'reortho': np.empty(maxiter),
                 'apply prec': np.empty(maxiter),
                 'extend Krylov': np.empty(maxiter),
                 'construct full basis': np.empty(maxiter),
                 'implicit QR': np.empty(maxiter),
                 'update solution': np.empty(maxiter),
                 'update residual': np.empty(maxiter)
                 }
    else:
        times = None

    if timer:
        start = time.time()

    xtype = upcast( A.dtype, b.dtype, x0.dtype )
    if M:
        xtype = upcast( xtype, M )
    if Ml:
        xtype = upcast( xtype, Ml )
    if Mr:
        xtype = upcast( xtype, Mr )

    # Compute M-norm of M*Ml*b.
    Mlb = _apply(Ml, b)
    MMlb = _apply(M, Mlb)
    norm_MMlb = _norm(Mlb, MMlb, inner_product = inner_product)

    # --------------------------------------------------------------------------
    # Init Lanczos and MINRES
    r0 = b - _apply(A, x0)
    Mlr0 = _apply(Ml, r0)
    MMlr0 = _apply(M, Mlr0)
    norm_MMlr0 = _norm(Mlr0, MMlr0, inner_product = inner_product)

    # initial relative residual norm 
    relresvec = [norm_MMlr0 / norm_MMlb]

    # compute error?
    if exact_solution is not None:
        errvec = [_norm(exact_solution - x0, inner_product = inner_product)]

    # --------------------------------------------------------------------------
    # Allocate and initialize the 'large' memory blocks.
    if return_basis or full_reortho:
        Vfull = np.c_[MMlr0 / norm_MMlr0, np.zeros([N,maxiter], dtype=xtype)]
        Pfull = np.c_[Mlr0 / norm_MMlr0, np.zeros([N,maxiter], dtype=xtype)]
        Hfull = np.zeros((maxiter+1,maxiter)) #scipy.sparse.lil_matrix( (maxiter+1,maxiter) )
    # Last and current Lanczos vector:
    V = np.c_[np.zeros(N), MMlr0 / norm_MMlr0]
    # M*v[i] = P[1], M*v[i-1] = P[0]
    P = np.c_[np.zeros(N), Mlr0 / norm_MMlr0]
    # Necessary for efficient update of yk:
    W = np.c_[np.zeros(N), np.zeros(N)]
    # some small helpers
    ts = 0.0           # (non-existing) first off-diagonal entry (corresponds to pi1)
    y  = [norm_MMlr0, 0] # first entry is (updated) residual
    G2 = np.eye(2)     # old givens rotation
    G1 = np.eye(2)     # even older givens rotation ;)
    k = 0

    # resulting approximation is xk = x0 + Mr*yk
    yk = np.zeros((N,1))
    xk = x0

    if timer:
        times['setup'][0] = time.time()-start

    # --------------------------------------------------------------------------
    # Lanczos + MINRES iteration
    # --------------------------------------------------------------------------
    while relresvec[-1] > tol and k < maxiter:
        # ---------------------------------------------------------------------
        # Lanczos
        if timer:
            start = time.time()
        tsold = ts
        z  = _apply(Mr, V[:,[1]])
        z  = _apply(A, z)
        z  = _apply(Ml, z)
        if timer:
            times['apply Ml*A*Mr'][k] = time.time()-start

        if timer:
            start = time.time()
        # tsold = inner_product(V[:,[0]], z)[0,0]
        z  = z - tsold * P[:,[0]]
        # Should be real! (diagonal element):
        td = inner_product(V[:,[1]], z)[0,0]
        if abs(td.imag) > 1.0e-12:
            print 'Warning (iter %d): abs(td.imag) = %g > 1e-12' % (k+1, abs(td.imag))
        td = td.real
        z  = z - td * P[:,[1]]
        if timer:
            times['Lanczos'][k] = time.time()-start

        ## local reorthogonalization
        #tsold2 = inner_product(V[0], z)
        #z   = z - tsold2 * P[0]
        #td2 = inner_product(V[1], z)
        #td  = td + td2
        #z   = z - td2*P[1]
        #tsold = tsold + tsold2

        if timer:
            start = time.time()
        # double reortho
        for l in xrange(0,2):
            # full reortho?
            # cost: (k+1)*(IP + AXPY)
            if full_reortho:
                # here we can (and should) orthogonalize against ALL THE
                # vectors (thus k+1).
                # http://memegenerator.net/instance/13779948
                # 
                for i in xrange(0,k+1):
                    ip = inner_product(Vfull[:,[i]], z)[0,0]
                    if abs(ip) > 1.0e-9:
                        print 'Warning (iter %d): abs(ip) = %g > 1.0e-9: The Krylov basis has become linearly dependent. Maxiter (%d) too large and tolerance too severe (%g)? dim = %d.' % (k+1, abs(ip), maxiter, tol, len(x0))
                    z = z - ip * Pfull[:,[i]]
            ## ortho against additional (deflation) vectors?
            ## cost: ndeflW*(IP + AXPY)
            #if deflW is not None:
            #    for i in xrange(0,deflW.shape[1]):
            #        ip = inner_product(deflW[:,[i]], z)[0,0]
            #        if abs(ip) > 1.0e-9:
            #            print 'Warning (iter %d): abs(ip) = %g > 1.0e-9: The Krylov basis has lost orthogonality to deflated space (deflW).' % (k+1, abs(ip))
            #        z = z - ip * deflW[:,[i]]
        if timer:
            times['reortho'][k] = time.time()-start
        
        # needed for QR-update:
        R = _apply(G1, [0, tsold])
        R = np.append(R, [0.0, 0.0])

        # Apply the preconditioner.
        if timer:
            start = time.time()
        v  = _apply(M, z)
        alpha = inner_product(z, v)[0,0]
        if abs(alpha.imag)>1e-12:
            print 'Warning (iter %d): abs(alpha.imag) = %g > 1e-12' % (k+1, abs(alpha.imag))
        alpha = alpha.real
        if alpha<0.0:
            print 'Warning (iter %d): alpha = %g < 0' % (k+1, alpha)
            alpha = 0.0
        ts = np.sqrt( alpha )
        if timer:
            times['apply prec'][k] = time.time()-start

        if timer:
            start = time.time()
        if ts > 0.0:
            P  = np.c_[P[:,[1]], z / ts]
            V  = np.c_[V[:,[1]], v / ts]
        else:
            P  = np.c_[P[:,[1]], np.zeros(N)]
            V  = np.c_[V[:,[1]], np.zeros(N)]
        if timer:
            times['extend Krylov'][k] = time.time()-start

        
        # store new vectors in full basis
        if timer:
            start = time.time()
        if return_basis or full_reortho:
            if ts>0.0:
                Vfull[:,[k+1]] = v / ts
                Pfull[:,[k+1]] = z / ts
            Hfull[k,k] = td        # diagonal
            Hfull[k+1,k] = ts      # subdiagonal
            if k+1 < maxiter:
                Hfull[k,k+1] = ts  # superdiagonal
        if timer:
            times['construct full basis'][k] = time.time()-start

        # ----------------------------------------------------------------------
        # (implicit) update of QR-factorization of Lanczos matrix
        if timer:
            start = time.time()
        R[2:4] = [td, ts]
        R[1:3] = _apply(G2, R[1:3])
        G1 = G2
        # compute new givens rotation.
        gg = np.linalg.norm( R[2:4] )
        gc = R[2] / gg
        gs = R[3] / gg
        G2 = np.array([ [gc,  gs],
                        [-gs, gc] ])
        R[2] = gg
        R[3] = 0.0
        y = _apply(G2, y)
        if timer:
            times['implicit QR'][k] = time.time()-start

        # ----------------------------------------------------------------------
        # update solution
        if timer:
            start = time.time()
        z  = (V[:,0:1] - R[0]*W[:,0:1] - R[1]*W[:,1:2]) / R[2]
        W  = np.c_[W[:,1:2], z]
        yk = yk + y[0] * z
        y  = [y[1], 0]
        if timer:
            times['update solution'][k] = time.time()-start

        # ----------------------------------------------------------------------
        # update residual
        if timer:
            start = time.time()
        if exact_solution is not None:
            xk = x0 + _apply(Mr, yk)
            errvec.append(_norm(exact_solution - xk, inner_product=inner_product))
        def compute_norm_r_exp(xk):
            xk = x0 + _apply(Mr, yk)
            r_exp = b - _apply(A, xk)
            r_exp = _apply(Ml, r_exp)
            # normalize residual before applying the preconditioner here.
            # otherwise norm_r_exp can become 0 exactly (pyamg seems to miss a
            # normalization step somewhere).
            r_exp /= norm_MMlb
            Mr_exp = _apply(M, r_exp)
            norm_r_exp = _norm(r_exp, Mr_exp, inner_product=inner_product)
            return xk, norm_r_exp

        if explicit_residual:
            xk, norm_r_exp = compute_norm_r_exp(yk)
            relresvec.append( norm_r_exp )
        else:
            relresvec.append(abs(y[0]) / norm_MMlb)

        # Compute residual explicitly if updated residual is below tolerance.
        if relresvec[-1] <= tol or k+1 == maxiter:
            norm_r_upd = relresvec[-1]
            # Compute the exact residual norm (if not yet done above)
            if not explicit_residual:
                xk, norm_r_exp = compute_norm_r_exp(yk)
                relresvec[-1] = norm_r_exp
            # No convergence of explicit residual?
            if relresvec[-1] > tol:
                # Was this the last iteration?
                if k+1 == maxiter:
                    print 'Warning (iter %d): No convergence! expl. res = %e >= tol =%e in last iter. (upd. res = %e)' \
                        % (k+1, relresvec[-1], tol, norm_r_upd)
                    info = 1
                else:
                    print ( 'Info (iter %d): Updated residual is below tolerance, '
                          + 'explicit residual is NOT!\n  (resEx=%g > tol=%g >= '
                          + 'resup=%g)\n' \
                          ) % (k+1, relresvec[-1], tol, norm_r_upd)

        if timer:
            times['update residual'][k] = time.time()-start

        # limit relative residual to machine precision (an exact 0 is rare but
        # seems to occur with pyamg...).
        relresvec[-1] = max(np.finfo(float).eps, relresvec[-1])
        k += 1
    # end MINRES iteration
    # --------------------------------------------------------------------------

    ret = { 'xk': xk,
            'info': info,
            'relresvec': relresvec
            }
    if exact_solution is not None:
        ret['errvec'] = errvec

    if return_basis:
        ret['Vfull'] = Vfull[:,0:k+1]
        ret['Pfull'] = Pfull[:,0:k+1]
        ret['Hfull'] = Hfull[0:k+1,0:k]
    if timer:
        # properly cut down times
        for key in times.keys():
            times[key] = times[key][:k]
        ret['times'] = times
    return ret
# ==============================================================================
def _direct_solve(A, rhs):
    '''Solve a (dense) equation system directly.'''
    if type(A) == np.float64:
        return rhs / A
    else:
        return np.linalg.solve(A, rhs)
# ==============================================================================
def get_projection(W, AW, b, x0, inner_product = _ipstd):
    """Get projection and appropriate initial guess for use in deflated methods.

    Arguments:
        W:  the basis vectors used for deflation (Nxk array).
        AW: A*W, where A is the operator of the linear algebraic system to be
            deflated. A has to be self-adjoint w.r.t. inner_product. Do not
            include the positive-definite preconditioner (argument M in MINRES)
            here. Let N be the dimension of the vector space the operator is
            defined on.
        b:  the right hand side of the linear system (array of length N).
        x0: the initial guess (array of length N).
        inner_product: the inner product also used for the deflated iterative
            method.

    Returns:
        P:  the projection to be used as _right_ preconditioner (e.g. Mr=P in
            MINRES). The preconditioned operator A*P is self-adjoint w.r.t. 
            inner_product.
            P(x)=x + W*inner_product(W, A*W)^{-1}*inner_product(A*W, x)
        x0new: an adapted initial guess s.t. the deflated iterative solver 
            does not break down (in exact arithmetics).
        AW: AW=A*W. This is returned in order to reduce the total number of
            matrix-vector multiplications with A.
    
    For nW = W.shape[1] = AW.shape[1] the computational cost is
    cost(get_projection): 2*cost(Pfun) + (nW^2)*IP
    cost(Pfun): nW*IP + (2/3)*nW^3 + nW*AXPY
    """
    # --------------------------------------------------------------------------
    def Pfun(x):
        '''Computes x - W * E\<AW,x>.'''
        return x - np.dot(W, _direct_solve(E, inner_product(AW, x)))
    # --------------------------------------------------------------------------
    
    # cost: (nW^2)*IP
    E = inner_product(W, AW)

    # cost: nW*IP + (2/3)*nW^3
    EWb = _direct_solve(E, inner_product(W, b))

    # Define projection operator.
    N = len(b)
    dtype = upcast(W.dtype, AW.dtype, b.dtype, x0.dtype)
    P = scipy.sparse.linalg.LinearOperator( [N,N], Pfun, matmat=Pfun,
                                            dtype=dtype)
    # Get updated x0.
    # cost: nW*AXPY + cost(Pfun)
    x0new = P*x0 +  np.dot(W, EWb)

    return P, x0new
# ==============================================================================
def get_ritz(W, AW, Vfull, Hfull, M=None, Minv=None, inner_product = _ipstd):
    """Compute Ritz pairs from a (possibly deflated) Lanczos procedure. 
    
    Arguments
        W:  a Nxk array. W's columns must be orthonormal w.r.t. the
            M-inner-product (inner_product(M^{-1} W, W) = I_k).
        AW: contains the result of A applied to W (passed in order to reduce #
            of matrix-vector multiplications with A).
        Vfull: a Nxn array. Vfull's columns must be orthonormal w.r.t. the
            M-inner-product. Vfull and Hfull must be created with a (possibly
            deflated) Lanczos procedure (e.g. CG/MINRES). For example, Vfull
            and Hfull can be obtained from MINRES applied to a linear system
            with the operator A, the inner product inner_product, the HPD
            preconditioner M and the right preconditioner Mr set to the
            projection obtained with get_projection(W, AW, ...).
        Hfull: see Vfull.
        M:  The preconditioner used in the Lanczos procedure.

        The arguments thus have to fulfill the following equations:
            AW = A*W.
            M*A*Mr*Vfull[:,0:-1] = Vfull*Hfull,
                 where Mr=get_projection(W, AW,...,inner_product).
            inner_product( M^{-1} [W,Vfull], [W,Vfull] ) = I_{k+n}.

    Returns:
        ritz_vals: an array with n+k Ritz values.
        ritz_vecs: a Nx(n+k) array where the ritz_vecs[:,i] is the 
            Ritz vector for the Ritz value ritz_vals[i]. The Ritz vectors
            also are orthonormal w.r.t. the M-inner-product, that is
                inner_product( M^{-1}*ritz_vecs, ritz_vecs ) = I_{k+n}.
        norm_ritz_res: an array with n+k residual norms. norm_ritz_res[i] is 
            the M^{-1}-norm of the residual
                M*A*ritz_vecs[:,i] - ritz_vals[i]*ritz_vecs[:,i].
            ritz_vals, ritz_vecs and norm_ritz_res are sorted s.t. the 
            residual norms are ascending.
    
    Under the above assumptions, [W, Vfull] is orthonormal w.r.t. the
    M-inner-product. Then the Ritz pairs w.r.t. the operator M*A, the basis [W,
    Vfull[:,0:-1]] and the M-inner-product are computed. Also the M-norm of the
    Ritz pair residual is computed. The computation of the residual norms do
    not need the application of the operator A, but the preconditioner has to
    be applied to the basis W. The computation of the residual norm may be
    unstable (it seems as if residual norms below 1e-8 cannot be achieved...
    note that the actual residual may be lower!).
    """
    nW = W.shape[1]
    nVfull = Vfull.shape[1]
    E = inner_product(W, AW)        # ~
    B1 = inner_product(AW, Vfull)   # can (and should) be obtained from MINRES
    B = B1[:, 0:-1]
    if scipy.sparse.issparse(Hfull):
        Hfull = Hfull.todense()

    # Compute residual norms.
    if nW>0:
        Einv = np.linalg.inv(E) # can (and should) be obtained from earlier computation

        # Apply preconditioner to AW (I don't see a way to get rid of this! -- André).
        # cost: nW*APPLM
        MAW = _apply(M, AW)
    else:
        N = W.shape[0]
        Einv = np.zeros( (0,0) )
        MAW = np.zeros( (N,0) )
    
    # Stack matrices appropriately: [E, B; B', Hfull(1:end-1,:) + B'*Einv*B].
    ritzmat = np.r_[    np.c_[E,B],
                        np.c_[B.T.conj(), Hfull[0:-1,:] + np.dot(B.T.conj(), np.dot(Einv, B))] 
                   ]

    # Compute Ritz values / vectors.
    from scipy.linalg import eigh
    lam, U = eigh(ritzmat)
    
    norm_ritz_res = np.zeros(lam.shape[0])

    # cost: (nW^2)*IP
    D1 = np.eye(nW)
    D = inner_product(AW, MAW)
    zeros = np.zeros((nW,nVfull))
    # Attention: CC should be HPD. However, this only holds if the 
    #            preconditioner was solved exactly 
    #            (then inner_product(Minv*W,W)=I)
    #            If the preconditioner is solved exactly, the 
    #            computation seems to be stable.
    CC = np.r_[ np.c_[ D1,             E,           zeros],
                np.c_[ E.T.conj(),     D,           B1],
                np.c_[ zeros.T.conj(), B1.T.conj(), np.eye(nVfull)] 
              ]

    for i in xrange(0,ritzmat.shape[0]):
        w = U[0:W.shape[1],[i]]
        v = U[W.shape[1]:,[i]]
        mu = lam[i]

        z = np.r_[ -mu*w, 
                    w + np.dot( Einv, np.dot(B, v)), 
                    np.dot(Hfull, v) - np.r_[mu*v, np.zeros((1,1))] ]
        z = np.reshape(z, (z.shape[0],1))
        CCz = np.dot(CC, z)
        res_ip = _ipstd(z, CCz)[0,0]
        if res_ip.imag > 1e-13:
            print 'Warning: res_ip.imag = %g > 1e-13' % res_ip.imag
            print '         Make sure that the preconditioner is solved \'exactly enough\'.'
        if res_ip.real < -1e-10:
            print 'Warning: res_ip.real = %g < -1e-10' % res_ip.real
            print '         Make sure that the preconditioner is solved \'exactly enough\'.'
        norm_ritz_res[i] = np.sqrt(abs(res_ip))

        # Explicit computation of residual (this part only works for M=I)
        #X = np.c_[W, Vfull[:,0:-1]]
        #V = np.dot(X, np.r_[w,v])
        #MAV = _apply(M,_apply(A, V))
        #res_explicit = MAV - lam[i]*V
        #zz = inner_product(_apply(Minv, res_explicit), res_explicit)[0,0]
        #assert( zz.imag<1e-13 )
        #print abs(norm_ritz_res[i] - np.sqrt(abs(zz)))
        #print 'Explicit residual: %g' % np.sqrt(abs(zz))
        if norm_ritz_res[i] < 1e-8:
            print 'Info: ritz value %g converged with residual %g.' % (lam[i], norm_ritz_res[i])

    # Sort Ritz values/vectors and residuals s.t. residual is ascending.
    sorti = np.argsort(abs(lam))
    ritz_vals = lam[sorti]
    ritz_vecs = np.dot(W, U[0:nW,sorti]) \
              + np.dot(Vfull[:,0:-1], U[nW:,sorti])
    norm_ritz_res  = norm_ritz_res[sorti]

    return ritz_vals, ritz_vecs, norm_ritz_res
# ==============================================================================
def gmres( A, b, x0,
           tol = 1e-5,
           maxiter = None,
           M = None,
           Ml = None,
           Mr = None,
           inner_product = _ipstd,
           explicit_residual = False,
           return_basis = False,
           exact_solution = None
         ):
    '''Preconditioned GMRES

    Solves   M*Ml*A*Mr*y = M*Ml*b,  x=Mr*y. 
    M has to be self-adjoint and positive-definite w.r.t. inner_product.
    
    Stopping criterion is
    ||M*Ml*(b-A*(x0+Mr*yk))||_{M^{-1}} / ||M*Ml*b||_{M^{-1}} <= tol
    
    Memory consumption is about maxiter+1 vectors for the Arnoldi basis.
    If M is used the memory consumption is 2*(maxiter+1).
    '''
    # TODO(Andre): errvec for exact_solution!=None
    # --------------------------------------------------------------------------
    def _compute_explicit_xk(H, V, y):
        '''Compute approximation xk to the solution.'''
        yy = np.linalg.solve(H, y)
        u  = _apply(Mr, np.dot(V, yy))
        xk = x0 + u
        return xk
    # --------------------------------------------------------------------------
    def _compute_explicit_residual( xk ):
        '''Compute residual explicitly.'''
        rk  = b - _apply(A, xk)
        rk  = _apply(Ml, rk)
        Mrk  = _apply(M, rk);
        norm_Mrk = _norm(rk, Mrk, inner_product=inner_product)
        return Mrk, norm_Mrk
    # --------------------------------------------------------------------------
    xtype = upcast( A.dtype, b.dtype, x0.dtype )
    if M is not None:
        xtype = upcast( xtype, M )
    if Ml is not None:
        xtype = upcast( xtype, Ml )
    if Mr is not None:
        xtype = upcast( xtype, Mr )

    N = len(b)
    if not maxiter:
        maxiter = N

    out = {}
    out['info'] = 0

    # get memory for working variables
    V = np.zeros([N, maxiter+1], dtype=xtype) # Arnoldi basis
    H = np.zeros([maxiter+1, maxiter], dtype=xtype) # Hessenberg matrix

    if M is not None:
        P = np.zeros([N,maxiter+1], dtype=xtype) # V=M*P 
    
    if return_basis:
        Horig = np.zeros([maxiter+1,maxiter], dtype=xtype)

    # initialize working variables
    Mlb = _apply(Ml, b)
    MMlb = _apply(M, Mlb)
    norm_MMlb = _norm(Mlb, MMlb, inner_product=inner_product)
    # This may only save us the application of Ml to the same vector again if
    # x0 is the zero vector.
    norm_x0 = _norm(x0, inner_product=inner_product)
    if norm_x0 > np.finfo(float).eps:
        r0 = b - _apply(A, x0)
        Mlr0 = _apply(Ml, r0)
        MMlr0 = _apply(M, Mlr0);
        norm_MMlr0 = _norm(Mlr0, MMlr0, inner_product=inner_product)
    else:
        x0 = np.zeros( (N,1) )
        Mlr0 = Mlb
        MMlr0 = MMlb
        norm_MMlr0 = norm_MMlb

    out['relresvec'] = np.empty(maxiter+1)

    V[:, [0]] = MMlr0 / norm_MMlr0
    if M is not None:
        P[:, [0]] = Mlr0 / norm_MMlr0
    out['relresvec'][0] = norm_MMlr0 / norm_MMlb
    # Right hand side of projected system:
    y = np.zeros( (maxiter+1,1), dtype=xtype )
    y[0] = norm_MMlr0
    # Givens rotations:
    G = []

    if exact_solution is not None:
        out['errorvec'] = np.empty(maxiter+1)
        out['errorvec'][0] = _norm(x0-exact_solution,
                                   inner_product=inner_product
                                   )

    k = 0
    while out['relresvec'][k] > tol and k < maxiter:
        # Apply operator Ml*A*Mr
        z = _apply(Ml, _apply(A, _apply(Mr, V[:, [k]])))

        # orthogonalize (MGS)
        for i in xrange(k+1):
            if M is not None:
                H[i, k] += inner_product(V[:, [i]], z)[0,0]
                z = z - H[i, k] * P[:, [i]]
            else:
                H[i, k] += inner_product(V[:, [i]], z)[0,0]
                z = z - H[i, k] * V[:, [i]]
        Mz = _apply(M, z);
        H[k+1, k] = _norm(z, Mz, inner_product=inner_product)
        if M is not None:
            P[:, [k+1]] = z / H[k+1, k]
        V[:, [k+1]] = Mz / H[k+1, k]
        if return_basis:
            Horig[0:k+2, [k]] = H[0:k+2, [k]]
        
        # Apply previous Givens rotations.
        for i in xrange(k):
            H[i:i+2, k] = _apply(G[i], H[i:i+2, k])

        # Compute and apply new Givens rotation.
        G.append(_givens(H[k, k], H[k+1, k]))
        H[k:k+2, k] = _apply(G[k], H[k:k+2, k])
        y[k:k+2] = _apply(G[k], y[k:k+2])

        # Update residual norm.
        if explicit_residual:
            xk = _compute_explicit_xk(H[:k+1, :k+1], V[:, :k+1], y[:k+1])
            Mrk, norm_Mrk = _compute_explicit_residual( xk )
            out['relresvec'][k+1] = norm_Mrk / norm_MMlb
        else:
            out['relresvec'][k+1] = abs(y[k+1]) / norm_MMlb

        # convergence of updated residual or maxiter reached?
        if out['relresvec'][k+1] < tol or k+1 == maxiter:
            norm_ur = out['relresvec'][k+1]

            if not explicit_residual:
                xk = _compute_explicit_xk(H[:k+1, :k+1], V[:, :k+1], y[:k+1])
                Mrk, norm_Mrk = _compute_explicit_residual( xk )
                out['relresvec'][k+1] = norm_Mrk / norm_MMlb

            # No convergence of expl. residual?
            if out['relresvec'][k+1] >= tol:
                # Was this the last iteration?
                if k+1 == maxiter:
                    print 'Warning (iter %d): No convergence! expl. res = %e >= tol =%e in last it. (upd. res = %e)' \
                        % (k+1, out['relresvec'][k+1], tol, norm_ur)
                    out['info'] = 1
                else:
                    print 'Warning (iter %d): Expl. res = %e >= tol = %e > upd. res = %e.' \
                        % (k+1, out['relresvec'][k+1], tol, norm_ur)

        k += 1

    out['relresvec'] = out['relresvec'][:k+1]
    out['xk'] = _compute_explicit_xk(H[:k,:k], V[:,:k], y[:k])
    if return_basis:
        out['Vfull'] = V[:, :k+1]
        out['Hfull'] = Horig[:k+1, :k]
        if M is not None:
            out['Pfull'] = P[:, :k+1]
    return out
# ==============================================================================
def _givens(a, b):
    '''Givens rotation
    [   c       s    ] * [a] = [r]
    [-conj(s) conj(c)]   [b]   [0]
    r real and non-negative.'''
    if abs(b) == 0:
        r = abs(a)
        c = a.conjugate() / r
        s = 0
    elif abs(a) == 0:
        r = abs(b)
        c = 0
        s = b.conjugate() / r
    elif abs(b) > abs(a):
        absb = abs(b)
        t = a.conjugate() / absb
        u = np.sqrt(1 + t.real**2 + t.imag**2)
        c = t / u
        s = (b.conjugate()/absb) / u
        r = absb * u
    else:
        absa = abs(a)
        t = b.conjugate()/absa
        u = np.sqrt(1 + t.real**2 + t.imag**2)
        c = (a.conjugate()/absa)/u
        s = t/u
        r = absa*u
    return np.array([[c, s],
                     [-s.conjugate(), c.conjugate()]])
# ==============================================================================
def orth_vec(v, W, inner_product=_ipstd):
    '''Orthogonalize v w.r.t. the orthonormal set W.'''
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    def _mod_gram_schmidt(v, W):
        for k in xrange(W.shape[1]):
            v -= inner_product(W[:,[k]],v) * W[:,[k]]
        return v
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    tau = inner_product(v, v)
    v = _mod_gram_schmidt(v, W)
    # Refine if necessary.
    # See
    # J. W. Daniel, W. B. Gragg, L. Kaufman, and G. W. Stewart.
    # Reorthogonalization and stable algorithms for updating the Gram-Schmidt
    # QR factorization; Math. Comp., 30:772-795, 1976.
    kappa = 0.25
    if inner_product(v, v) / tau < kappa**2:
        v = _mod_gram_schmidt(v, W)

    return v
# ==============================================================================
def qr(W, inner_product=_ipstd):
    '''QR-decomposition w.r.t. given inner-product
    
    [Q,R] = qr(W, inner_product) yields Q and R such that W=dot(Q,R) and
    inner_product(Q,Q)=I.
    '''
    m = W.shape[0]
    n = W.shape[1]
    Q = np.zeros( (m,n), dtype=W.dtype)
    R = np.zeros( (n,n), dtype=W.dtype)

    for i in xrange(0,n):
        Q[:,[i]] = W[:,[i]]
        for j in xrange(0,i):
            R[j,i] = inner_product(Q[:,[j]], Q[:,[i]])[0,0]
            Q[:,[i]] -= R[j,i] * Q[:,[j]]
        R[i,i] = inner_product(Q[:,[i]],Q[:,[i]])[0,0]
        if (R[i,i].imag > 1e-10):
            print 'R[i,i].imag = %g > 1e-10' % R[i,i].imag
        if (R[i,i].real < -1e-14):
            print 'R[i,i].real = %g < -1e-14' % R[i,i].real
        R[i,i] = np.sqrt(abs(R[i,i]))
        Q[:,[i]] /= R[i,i]

    return Q, R


# ==============================================================================
def newton( x0,
            model_evaluator,
            nonlinear_tol = 1.0e-10,
            newton_maxiter = 20,
            linear_solver = minres,
            linear_solver_maxiter = None,
            linear_solver_extra_args = {},
            forcing_term = 'constant',
            eta0 = 1.0e-1,
            eta_min = 1.0e-6,
            eta_max = 1.0e-2,
            alpha = 1.5, # only used by forcing_term='type 2'
            gamma = 0.9, # only used by forcing_term='type 2'
            use_preconditioner = False,
            deflate_ix = False,
            num_deflation_vectors = 0,
            debug = False
          ):
    '''Newton's method with different forcing terms.
    '''
    from scipy.constants import golden

    # some initializations
    error_code = 0
    k = 0

    x = x0.copy()
    Fx = model_evaluator.compute_f( x )
    Fx_norms = [ _norm( Fx, inner_product=model_evaluator.inner_product ) ]
    eta_previous = None
    W = np.zeros( (len(x),0 ) )
    linear_relresvecs = []
    while Fx_norms[-1] > nonlinear_tol and k < newton_maxiter:
        if debug:
            print '--------- Next Newton step ---------'
        # Linear tolerance is given by
        #
        # "Choosing the Forcing Terms in an Inexact Newton Method (1994)"
        # -- Eisenstat, Walker
        # http://citeseer.ist.psu.edu/viewdoc/summary?doi=10.1.1.15.3196
        #
        # See also
        # "NITSOL: A Newton Iterative Solver for Nonlinear Systems"
        # http://epubs.siam.org/sisc/resource/1/sjoce3/v19/i1/p302_s1?isAuthorized=no
        if eta_previous is None or forcing_term == 'constant':
            eta = eta0
        elif forcing_term == 'type 1':
            # linear_relresvec[-1] \approx tol, so this could be replaced.
            eta = abs(Fx_norms[-1] - out["relresvec"][-1]) / Fx_norms[-2]
            eta = max( eta, eta_previous**golden, eta_min )
            eta = min( eta, eta_max )
        elif forcing_term == 'type 2':
            eta = gamma * (Fx_norms[-1] / Fx_norms[-2])**alpha
            eta = max( eta, gamma * eta_previous**alpha, eta_min )
            eta = min( eta, eta_max )
        else:
            raise ValueError('Unknown forcing term \'%s\'. Abort.')
        eta_previous = eta
        if debug:
            print 'New tolerance for linear solver is %g.' % eta

        # Setup linear problem.
        jacobian = model_evaluator.get_jacobian( x )
        initial_guess = np.zeros( (len(x),1) )
        rhs = -Fx

        if use_preconditioner:
            M = model_evaluator.get_preconditioner(x)
            Minv = model_evaluator.get_preconditioner_inverse(x)
        else:
            M = None
            Minv = None

        def Minner_product(x,y):
            return model_evaluator.inner_product(_apply(M,x), y)

        W, R = qr(W, inner_product=Minner_product)

        # Conditionally deflate the nearly-null vector i*x.
        # Attention: if the preconditioner is later solved inexactly
        #            then W will be orthonormal w.r.t. another inner
        #            product! This may affect the computation of ritz
        #            pairs and their residuals.
        if deflate_ix:
            u = 1j * x
            Mu = _apply(M, u)
            nrm_u = _norm(u, Mu, inner_product = model_evaluator.inner_product)
            u /= nrm_u

            u = orth_vec(u, W, Minner_product)

            # normalize u in the M-norm
            Mu = _apply(M, u)
            nrm_u = _norm(u, Mu, inner_product = model_evaluator.inner_product)
            if nrm_u > 1.0e-10:
                u = u / nrm_u
                W = np.c_[W, u]

        if W.shape[1] > 0:
            AW = jacobian * W
            P, x0new = get_projection(W, AW, rhs, initial_guess,
                                      inner_product = model_evaluator.inner_product
                                      )
            if debug:
                print 'dim of deflation space: %d' % W.shape[1]
                print '||I-ip(W,W)|| = %g' % np.linalg.norm(np.eye(W.shape[1])-Minner_product(W,W))
        else:
            AW = np.zeros((len(x), 0))
            P = None
            x0new = initial_guess
        
        if num_deflation_vectors > 0:
            return_basis = True

            # limit to 0.5 GB memory for Vfull/Pfull (together)
            from math import floor
            maxmem = 0.5*(2**30) # bytes
            linear_solver_maxiter = min(linear_solver_maxiter, int(floor(maxmem/(2*16*len(x)))))
        else:
            return_basis = False

        # Solve the linear system.
        out = linear_solver(jacobian,
                            rhs,
                            x0new,
                            maxiter = linear_solver_maxiter,
                            Mr = P,
                            M = Minv,
                            tol = eta,
                            inner_product = model_evaluator.inner_product,
                            return_basis = return_basis,
                            explicit_residual = False,
                            **linear_solver_extra_args
                            )
        if debug:
            print 'Linear solver \'%s\' performed %d iterations.' %(linear_solver.__name__, len(out['relresvec'])-1)

        # make sure the solution is alright
        if out['info'] != 0:
            print 'Warning (newton): solution from linear solver has info = %d != 0' % out['info']

        np.set_printoptions(linewidth=150)
        if ('Vfull' in out.keys()) and ('Hfull' in out.keys()):
            if debug:
                MVfull = out['Pfull'] if ('Pfull' in out.keys()) else out['Vfull']
                print '||ip(Vfull,W)|| = %g' % \
                    np.linalg.norm(model_evaluator.inner_product(MVfull, W))
                print '||I-ip(Vfull,Vfull)|| = %g' % \
                    np.linalg.norm(np.eye(out['Vfull'].shape[1]) - model_evaluator.inner_product(MVfull, out['Vfull']))
                # next one is time-consuming, uncomment if needed
                #print '||Minv*A*P*V - V_*H|| = %g' % \
                #    np.linalg.norm(_apply(Minv, _apply(jacobian, _apply(P, out['Vfull'][:,0:-1]))) - np.dot(out['Vfull'], out['Hfull']) )

            if num_deflation_vectors > 0:
                ritz_vals, ritz_vecs, norm_ritz_res = get_ritz(W, AW, out['Vfull'], out['Hfull'],
                                                           M = Minv, Minv=M,
                                                           inner_product = model_evaluator.inner_product)
                # Ritz vectors are ordered such that the ones with the smallest
                # residuals come first.
                if debug:
                    print '||I-ip(ritz_vecs,ritz_vecs)|| = %g' % np.linalg.norm(np.eye(ritz_vecs.shape[1])-Minner_product(ritz_vecs,ritz_vecs))
                W = ritz_vecs[:,0:min(num_deflation_vectors, ritz_vecs.shape[1])]
                if debug:
                    print '||I-ip(Wnew,Wnew)|| = %g' % np.linalg.norm(np.eye(W.shape[1])-Minner_product(W,W))
                    print 'min/max norm of ritz res: %g / %g' % (min(norm_ritz_res), max(norm_ritz_res))
            else:
                W = np.zeros( (len(x),0) )
        else:
            W = np.zeros( (len(x),0) )

        # save the convergence history
        linear_relresvecs.append( out['relresvec'] )

        # perform the Newton update
        x += out['xk']

        # do the household
        k += 1
        Fx = model_evaluator.compute_f( x )
        Fx_norms.append(_norm(Fx, inner_product=model_evaluator.inner_product))
        if debug:
            print 'New Newton residual is %g.' % Fx_norms[-1]

    if k == newton_maxiter:
        error_code = 1

    return x, error_code, Fx_norms, linear_relresvecs
# ==============================================================================
def jacobi_davidson(A,
                    v0, # starting vector
                    tol = 1e-5,
                    maxiter = None,
                    M = None,
                    inner_product = _ipstd
                    ):
    '''Jacobi-Davidson for the largest-magnitude eigenvalue of a
    self-adjoint operator.'''
    xtype = upcast( A.dtype, v0.dtype )
    num_unknowns = len(v0)
    if maxiter is None:
        maxiter = num_unknowns
    t = v0
    # Set up fields.
    V = np.empty((num_unknowns, maxiter), dtype=xtype)
    AV = np.empty((num_unknowns, maxiter), dtype=xtype)
    B = np.empty((maxiter, maxiter), dtype=float)

    resvec = []
    info = 1
    for m in xrange(maxiter):
        # orthgonalize t w.r.t. to the basis V
        t = orth_vec(t, V[:,0:m], inner_product=inner_product)

        # normalize
        norm_t = np.sqrt(inner_product(t, t))[0,0]
        assert norm_t > 1.0e-10, '||t|| = 0. Breakdown.'

        V[:,[m]] = t / norm_t
        AV[:,[m]] = _apply(A, V[:,[m]])

        # B = <V,AV>.
        # Only fill the lower triangle of B.
        for i in xrange(m+1):
            alpha = inner_product(V[:, [i]], AV[:,[m]])[0,0]
            assert alpha.imag < 1.0e-10, 'A not self-adjoint?'
            B[m, i] = alpha.real

        # Compute the largest eigenpair of B.
        from scipy.linalg import eigh
        Theta, S = eigh(B[0:m+1,0:m+1], lower=True)

        # Extract the largest-magnitude one.
        index = np.argmax(abs(Theta))
        theta = Theta[index]
        s = S[:,[index]]
        # normalize s in the inner product
        norm_s = np.sqrt(inner_product(s, s))[0,0]
        assert norm_s > 1.0e-10, '||s|| = 0. Breakdown.'
        s /= norm_s

        # Get u, Au.
        u = np.dot(V[:,0:m+1], s)
        Au = np.dot(AV[:,0:m+1], s)

        # Compute residual.
        res = Au - theta*u
        resvec.append(np.sqrt(inner_product(res, res)[0,0]))

        if resvec[-1] < tol:
            info = 0
            break
        else:
            # (Approximately) solve for t\ortho u from
            # (I-uu*)(A-theta I)(I-uu*) t = -r.
            def _shifted_projected_operator(A, u, theta):
                def _apply_proj(phi):
                    return phi - u * inner_product(u, phi)
                def _apply_shifted_projected_operator(phi):
                    return _apply_proj(A*_apply_proj(phi) - theta*_apply_proj(phi))
                return LinearOperator((num_unknowns, num_unknowns),
                                      _apply_shifted_projected_operator,
                                      dtype = A.dtype
                                      )
            assert abs(inner_product(u, res)) < 1.0e-10
            out = minres(_shifted_projected_operator(A, u, theta),
                         -res,
                         x0 = np.zeros((num_unknowns,1)),
                         tol = 1.0e-8,
                         M = M,
                         #Minv = None,
                         #Ml = _proj(u),
                         #Mr = _proj(u),
                         maxiter = num_unknowns,
                         inner_product = inner_product
                         )
            assert out[1] == 0, 'MINRES did not converge.'
            t = out[0]
            assert abs(inner_product(t, u)[0,0]) < 1.0e-10, abs(inner_product(t, u))[0,0]

    return theta, u, info, resvec
# ==============================================================================
def poor_mans_continuation( x0,
                            model_evaluator,
                            initial_parameter_value,
                            initial_step_size = 1.0e-2,
                            minimal_step_size = 1.0e-6,
                            maximum_step_size = 1.0e-1,
                            max_steps = 1000,
                            nonlinear_tol = 1.0e-10,
                            max_newton_iters = 5,
                            adaptivity_aggressiveness = 1.0
                          ):
    '''Poor man's parameter continuation. With adaptive step size.
    If the previous step was unsucessful, the step size is cut in half,
    but if the step was sucessful this strategy increases the step size based
    on the number of nonlinear solver iterations required in the previous step.
    In particular, the new step size \f$\Delta s_{new}\f$ is given by

       \Delta s_{new} = \Delta s_{old}\left(1 + a\left(\frac{N_{max} - N}{N_{max}}\right)^2\right).
    '''

    # write header of the statistics file
    stats_file = open( 'continuationData.dat', 'w' )
    stats_file.write( '# step    parameter     norm            Newton iters\n' )
    stats_file.flush()

    parameter_value = initial_parameter_value
    x = x0

    current_step_size = initial_step_size

    for k in xrange( max_steps ):
        print "Continuation step %d (parameter=%e)..." % ( k, parameter_value )

        # Try to converge to a solution and adapt the step size.
        converged = False
        while current_step_size > minimal_step_size:
            x_new, error_code, iters = newton( x,
                                               model_evaluator,
                                               nonlinear_tol = nonlinear_tol,
                                               max_iters = max_newton_iters
                                             )
            if error_code != 0:
                current_step_size *= 0.5
                print "Continuation step failed (error code %d). Setting step size to %e." \
                      % ( error_code, current_step_size )
            else:
                current_step_size *= 1.0 + adaptivity_aggressiveness * \
                                           (float(max_newton_iters-iters)/max_newton_iters)**2
                converged = True
                x = x_new
                print "Continuation step success!"
                break

        if not converged:
            print "Could not find a solution although the step size was %e. Abort." % current_step_size
            break


        stats_file.write( '  %4d    %.5e   %.5e    %d\n' %
                          ( k, parameter_value, model_evaluator.energy(x), iters )
                        )
        stats_file.flush()
        #model_evaluator.write( x, "step" + str(k) + ".vtu" )

        parameter_value += current_step_size
        model_evaluator.set_parameter( parameter_value )
        
    stats_file.close()
    
    print "done."
    return
# ==============================================================================
