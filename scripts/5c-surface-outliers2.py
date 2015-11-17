#!/usr/bin/python

# compute neighbors in pixel space, then compute 'cone' shape metric
# in 3d sba space.  Outliers will typically be separted from their
# neighbors in 3d space ... i.e. long cone depth relative to base
# size.

import sys
sys.path.insert(0, "/usr/local/opencv-2.4.11/lib/python2.7/site-packages/")

import argparse
import commands
import cPickle as pickle
import cv2
import fnmatch
import itertools
#import json
import math
import matplotlib.pyplot as plt
import numpy as np
import os.path
from progress.bar import Bar
import scipy.spatial

sys.path.append('../lib')
import Matcher
import Pose
import ProjectMgr
import SRTM
import transformations


def meta_stats(report):
    sum = 0.0
    count = len(report)
    for line in report:
        value = line[0]
        sum += value
    average = sum / len(report)
    print "average value = %.2f" % (average)

    sum = 0.0
    for line in report:
        value = line[0]
        diff = average - value
        sum += diff**2
    stddev = math.sqrt(sum / count)
    print "standard deviation = %.2f" % (stddev)
    return average, stddev

parser = argparse.ArgumentParser(description='Compute Delauney triangulation of matches.')
parser.add_argument('--project', required=True, help='project directory')
parser.add_argument('--stddev', default=5, type=int, help='standard dev threshold')
args = parser.parse_args()

proj = ProjectMgr.ProjectMgr(args.project)
proj.load_image_info()
proj.load_features()

print "Loading original (direct) matches ..."
matches_direct = pickle.load( open( args.project + "/matches_direct", "rb" ) )

print "Loading fitted (sba) matches..."
matches_sba = pickle.load( open( args.project + "/matches_sba", "rb" ) )

def compute_surface_outliers():
    # start with a clean slate
    for image in proj.image_list:
        image.feat_3d = []
        image.feat_uv = []
        image.feat_match_idx = []
    
    # iterate through the sba match dictionary and build a per-image
    # list of 3d feature points with corresponding 2d uv coordinates
    print "Building per-image structures..."
    for i, match in enumerate(matches_sba):
        # print i, match
        ned = match[0]
        for p in match[1:]:
            image = proj.image_list[ p[0] ]
            image.feat_3d.append( ned )
            image.feat_uv.append( list(image.kp_list[p[1]].pt) )
            # print " ", image.kp_list[p[1]].pt
            image.feat_match_idx.append( i )
   
    print "Processing images..."
    report = []
    for index, image in enumerate(proj.image_list):
        print image.name, len(image.feat_uv)
        if len(image.feat_uv) < 3:
            continue
        debug = False
        if debug:
            size = len(image.feat_uv)
            min_dist = image.width
            count = 0
            for i in range(size):
                p0 = np.array(image.feat_uv[i])
                for j in range(i+1, size):
                    p1 = np.array(image.feat_uv[j])
                    dist = np.linalg.norm(p0-p1)
                    if dist < 000001:
                        print index, p0, p1
                        count += 1
                    if dist < min_dist:
                        min_dist = dist
            print "minimum feature dist =", min_dist, "count =", count
        tri = scipy.spatial.Delaunay(np.array(image.feat_uv))
        
        # look for outliers by computing the 3d world shape of the
        # pseudo-cone formed by a point with it's neighbors found in
        # uv space.  This assumes photos were taken from a mostly top
        # down vantage point.

        # print image.name
        # print " neighbors:", len(tri.vertex_neighbor_vertices[0]), len(tri.vertex_neighbor_vertices[1])
        # print " neighbor[0]:\n", tri.vertex_neighbor_vertices[0][0], tri.vertex_neighbor_vertices[0][1]
        indices, indptr = tri.vertex_neighbor_vertices
        for i in range(len(tri.points)):
            pi = np.array( image.feat_3d[i] )
            neighbors = indptr[indices[i]:indices[i+1]]
            if len(neighbors) < 2:
                continue
            pj0 = np.array( image.feat_3d[neighbors[0]] )
            sum_p = np.zeros(3)
            sum_p += pj0
            max_dist = 0.0
            for j in neighbors[1:]:
                pj = np.array( image.feat_3d[j] )
                sum_p += pj
                dist = np.linalg.norm(pj - pj0)
                if dist > max_dist:
                    max_dist = dist
            avg_p = sum_p / len(neighbors)
            cone_dist = np.linalg.norm(pi - avg_p)
            if max_dist > 0.001:
                metric = cone_dist / max_dist
            else:
                metric = 0.0
            # print i, metric
            # assemble a list of value vs. index into original match list
            report.append( (metric, image.feat_match_idx[i]) )

    average, stddev = meta_stats(report)
    report = sorted(report, key=lambda fields: abs(fields[0]), reverse=True)

    delete_list = []
    for line in report:
        metric = line[0]
        index = line[1]
        if abs(average - metric) >= args.stddev * stddev:
            print "index=", index, "metric=", metric
            delete_list.append( index )

    delete_list = sorted(delete_list, reverse=True)
    for index in delete_list:
        #print "deleting", index
        matches_direct.pop(index)
        matches_sba.pop(index)

    return len(delete_list)

deleted_sum = 0
result = compute_surface_outliers()
while result > 0:
    deleted_sum += result
    result = compute_surface_outliers()

if deleted_sum > 0:
    result=raw_input('Remove ' + str(deleted_sum) + ' outliers from the original matches? (y/n):')
    if result == 'y' or result == 'Y':

        # write out the updated match dictionaries
        print "Writing original matches..."
        pickle.dump(matches_direct, open(args.project+"/matches_direct", "wb"))

        print "Writing sba matches..."
        pickle.dump(matches_sba, open(args.project+"/matches_sba", "wb"))