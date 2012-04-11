#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''Solve the Ginzburg--Landau equation.
'''
# ==============================================================================
import numpy as np

import pyginla.numerical_methods as nm
import pyginla.ginla_modelevaluator as gm
import voropy
# ==============================================================================
def _main():
    args = _parse_input_arguments()

    # read the mesh
    print 'Reading the mesh...',
    mesh, point_data, field_data = voropy.read( args.filename )
    print 'done.'

    # build the model evaluator
    if 'mu' in field_data:
        mu = field_data['mu']
        print 'Using  mu = %g  as found in file.' % mu
    else:
        mu = 1.0
        print 'No parameter \'mu\' found in file. Using  mu = %g.' % mu
    ginla_modeleval = gm.GinlaModelEvaluator(mesh, point_data['A'], mu)

    # initial guess
    num_nodes = len(mesh.node_coords)
    if 'psi' in point_data:
        point_data['psi'] = point_data['psi'][:,0] \
                          + 1j * point_data['psi'][:,1]
        psi0 = np.reshape(point_data['psi'], (num_nodes,1))
    else:
        psi0 = 1.0 * np.ones((num_nodes,1), dtype=complex)
        #alpha = 0.3
        #kx = 2
        #ky = 0.5
        #for i, node in enumerate(mesh.node_coords):
            #psi0[i] = alpha * np.cos(kx * node[0]) * np.cos(ky * node[1])
    newton_out = newton(ginla_modeleval, psi0)
    print 'Newton residuals:', newton_out['Newton residuals']

    if args.show:
        import matplotlib.pyplot as pp
        multiplot_data_series( newton_out['linear relresvecs'] )
        #pp.xlim([0,45])
        pp.show()

    #import matplotlib2tikz
    #matplotlib2tikz.save('minres-prec-defl.tex')

    # write the solution to a file
    ginla_modeleval.mesh.write('solution.e', {'psi': newton_out['x']})
    # energy of the state
    print 'Energy of the final state: %g.' % ginla_modeleval.energy( newton_out['x'] )

    return
# ==============================================================================
def newton(ginla_modeleval, psi0, debug=True):
    '''Solve with Newton.
    '''

    print 'Performing Newton iteration...'
    # perform newton iteration
    newton_out = nm.newton(psi0,
                           ginla_modeleval,
                           linear_solver = nm.minres,
                           linear_solver_maxiter = 1000, #2*len(psi0),
                           linear_solver_extra_args = {},
                           nonlinear_tol = 1.0e-10,
                           forcing_term = 'constant', #'constant', 'type1', 'type 2'
                           eta0 = 1.0e-10,
                           use_preconditioner = True,
                           deflation_generators = [ lambda x: 1j*x ],
                           num_deflation_vectors = 0,
                           debug=debug,
                           newton_maxiter = 30
                           )
    print ' done.'
    #assert( newton_out['info'] == 0 )

    return newton_out
# ==============================================================================
def multiplot_data_series( list_of_data_vectors ):
    '''Plot a list of data vectors with increasing black value.'''
    import matplotlib.pyplot as pp
    num_plots = len( list_of_data_vectors )
    for k, relresvec in enumerate(list_of_data_vectors):
        pp.semilogy(relresvec, color=str(1.0 - float(k+1)/num_plots))
    pp.xlabel('MINRES step')
    pp.ylabel('||r||/||b||')
    return
# ==============================================================================
def _parse_input_arguments():
    '''Parse input arguments.
    '''
    import argparse

    parser = argparse.ArgumentParser( description = 'Find solutions to the Ginzburg--Landau equation.' )

    parser.add_argument('filename',
                        metavar = 'FILE',
                        type    = str,
                        help    = 'ExodusII file containing the geometry and initial state'
                        )

    parser.add_argument('--show', '-s',
                        action = 'store_true',
                        default = False,
                        help    = 'show the relative residuals of each linear iteration (default: False)'
                        )
    

    return parser.parse_args()
# ==============================================================================
if __name__ == '__main__':
    _main()
# ==============================================================================