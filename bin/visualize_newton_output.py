#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
#  Copyright (c) 2012--2014, Nico Schlömer, <nico.schloemer@gmail.com>
#  All rights reserved.
#
#  This file is part of PyNosh.
#
#  PyNosh is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  PyNosh is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with PyNosh.  If not, see <http://www.gnu.org/licenses/>.
#
import yaml
import matplotlib
# Use the AGG backend to make sure that we don't need
# $DISPLAY to plot something (to files).
matplotlib.use('agg')
import matplotlib.pyplot as pp
import matplotlib2tikz


def _main():
    args = _parse_input_arguments()

    # read the file
    handle = open(args.filename)
    data = yaml.load(handle)
    handle.close()

    # Plot relresvecsi.
    #pp.subplot(121)
    # Mind that the last Newton datum only contains the final ||F||.
    num_newton_steps = len(data['Newton results']) - 1
    for k in xrange(num_newton_steps):
        pp.semilogy(
            data['Newton results'][k]['relresvec'],
            color=str(1.0 - float(k+1)/num_newton_steps)
            )
    pp.xlabel('Krylov step')
    pp.ylabel('||r||/||b||')
    pp.title('Krylov: %s    Prec: %r    ix-defl: %r    extra defl: %r    ExpRes: %r    Newton iters: %d' %
             (data['krylov'], data['preconditioner type'], data['ix deflation'],
              data['extra deflation'], data['explicit residual'], num_newton_steps)
             )
    if args.xmax:
        pp.xlim([0, args.xmax])
    pp.ylim([1e-10, 10])

    # Write the info out to files.
    if args.imgfile:
        pp.savefig(args.imgfile)
    if args.tikzfile:
        matplotlib2tikz.save(args.tikzfile)
    return


def _parse_input_arguments():
    '''Parse input arguments.
    '''
    import argparse

    parser = argparse.ArgumentParser(description='Visualize Newton output.')

    parser.add_argument('filename',
                        metavar='FILE',
                        type=str,
                        help='Newton data file'
                        )

    parser.add_argument('--xmax', '-x',
                        type=int,
                        default=None,
                        help='maximum number of iterations'
                        )

    parser.add_argument('--imgfile', '-i',
                        metavar='IMG_FILE',
                        required=True,
                        default=None,
                        const=None,
                        type=str,
                        help='Image file to store the results'
                        )

    parser.add_argument('--tikzfile', '-t',
                        metavar='TIKZ_FILE',
                        required=True,
                        default=None,
                        const=None,
                        type=str,
                        help='TikZ file to store the results'
                        )
    return parser.parse_args()


if __name__ == '__main__':
    _main()
