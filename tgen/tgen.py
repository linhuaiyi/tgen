#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Generating T-trees from dialogue acts.

Usage: ./tgen.py <action> <argument1 ...>

Actions:

candgen_train -- train candidate generator (probability distributions)
    - arguments: [-p prune_threshold] train-das train-ttrees output-model

logregrank_create_data -- create training data for logistic regression ranker
    - arguments: [-h use-headers] train-das train-ttrees candgen-model ranker-config output-train-data

logregrank_train -- train logistic regression local ranker
    - arguments: ranker-config ranker-train-data output-model

percrank_train -- train perceptron global ranker
    - arguments: [-d debug-output] [-c candgen-model] ranker-config train-das train-ttrees output-model

sample_gen -- generate using the given candidate generator and ranker
    - arguments: [-n trees-per-da] [-r ranker-model] [-o oracle-eval-ttrees] [-w output-ttrees] candgen-model test-das

asearch_gen -- generate using the A*search sentence planner
    - arguments: [-e oracle-eval-ttrees] [-d debug-output] [-w output-ttrees] [-c config] candgen-model percrank-model test-das
"""

from __future__ import unicode_literals
import random
import sys

from alex.components.nlg.tectotpl.block.write.yaml import YAML as YAMLWriter
from flect.logf import log_info

from futil import read_das, read_ttrees, chunk_list, ttrees_from_doc
from candgen import RandomCandidateGenerator
from rank import LogisticRegressionRanker, PerceptronRanker
from planner import SamplingPlanner, ASearchPlanner
from flect.config import Config
from getopt import getopt
from eval import tp_fp_fn, f1_from_counts, p_r_f1_from_counts
from alex.components.nlg.tectotpl.core.util import file_stream


def candgen_train(args):
    opts, files = getopt(args, 'p:')
    prune_threshold = 1
    for opt, arg in opts:
        if opt == '-p':
            prune_threshold = int(arg)

    if len(files) != 3:
        sys.exit(__doc__)
    fname_da_train, fname_ttrees_train, fname_cand_model = files

    log_info('Training candidate generator...')
    candgen = RandomCandidateGenerator({'prune_threshold': prune_threshold})
    candgen.train(fname_da_train, fname_ttrees_train)
    candgen.save_model(fname_cand_model)


def logregrank_create_data(args):
    opts, files = getopt(args, 'h:')
    header_file = None
    for opt, arg in opts:
        if opt == '-h':
            header_file = arg
    if len(files) != 5:
        sys.exit(__doc__)
    fname_da_train, fname_ttrees_train, fname_cand_model, fname_rank_config, fname_rank_train = files

    log_info('Creating data for ranker...')
    candgen = RandomCandidateGenerator({})
    candgen.load_model(fname_cand_model)
    rank_config = Config(fname_rank_config)
    ranker = LogisticRegressionRanker(rank_config)
    ranker.create_training_data(fname_ttrees_train, fname_da_train, candgen, fname_rank_train,
                                header_file=header_file)


def logregrank_train(args):
    if len(args) != 3:
        sys.exit(__doc__)

    fname_rank_config, fname_rank_train, fname_rank_model = args
    log_info('Training logistic regression ranker...')

    rank_config = Config(fname_rank_config)
    ranker = LogisticRegressionRanker(rank_config)
    ranker.train(fname_rank_train)
    ranker.save_to_file(fname_rank_model)


def percrank_train(args):
    opts, files = getopt(args, 'c:d:')
    debug_out = None
    candgen_model = None

    for opt, arg in opts:
        if opt == '-d':
            debug_out = file_stream(arg, mode='w')
        elif opt == '-c':
            candgen_model = arg

    if len(files) != 4:
        sys.exit(__doc__)

    fname_rank_config, fname_train_das, fname_train_ttrees, fname_rank_model = files
    log_info('Training perceptron ranker...')

    rank_config = Config(fname_rank_config)
    rank_config['debug_out'] = debug_out
    if candgen_model:
        rank_config['candgen_model'] = candgen_model
    ranker = PerceptronRanker(rank_config)
    ranker.train(fname_train_das, fname_train_ttrees)
    ranker.save_to_file(fname_rank_model)


def sample_gen(args):
    opts, files = getopt(args, 'r:n:o:w:')
    num_to_generate = 1
    ranker_model = None
    oracle_eval_file = None
    fname_ttrees_out = None

    for opt, arg in opts:
        if opt == '-r':
            ranker_model = arg
        elif opt == '-n':
            num_to_generate = int(arg)
        elif opt == '-o':
            oracle_eval_file = arg
        elif opt == '-w':
            fname_ttrees_out = arg

    if len(files) != 2:
        sys.exit(__doc__)
    fname_cand_model, fname_da_test = files

    # load model
    log_info('Initializing...')
    candgen = RandomCandidateGenerator({})
    candgen.load_model(fname_cand_model)

    if ranker_model is not None:
        ranker = LogisticRegressionRanker.load_from_file(ranker_model)
    else:
        ranker = candgen

    tgen = SamplingPlanner({'candgen': candgen, 'ranker': ranker})
    # generate
    log_info('Generating...')
    gen_doc = None
    das = read_das(fname_da_test)
    for da in das:
        for _ in xrange(num_to_generate):  # repeat generation n times
            gen_doc = tgen.generate_tree(da, gen_doc)

    # evaluate if needed
    if oracle_eval_file is not None:
        log_info('Evaluating oracle F1...')
        log_info('Loading gold data from ' + oracle_eval_file)
        gold_trees = ttrees_from_doc(read_ttrees(oracle_eval_file), tgen.language, tgen.selector)
        gen_trees = ttrees_from_doc(gen_doc, tgen.language, tgen.selector)
        log_info('Gold data loaded.')
        correct, predicted, gold = 0, 0, 0
        for gold_tree, gen_trees in zip(gold_trees, chunk_list(gen_trees, num_to_generate)):
            # find best of predicted trees (in terms of F1)
            _, tc, tp, tg = max([(f1_from_counts(c, p, g), c, p, g) for c, p, g
                                 in map(lambda gen_tree: tp_fp_fn(gold_tree, gen_tree),
                                        gen_trees)],
                                key=lambda x: x[0])
            correct += tc
            predicted += tp
            gold += tg
        # evaluate oracle F1
        log_info("Oracle Precision: %.6f, Recall: %.6f, F1: %.6f" % p_r_f1_from_counts(correct, gold, predicted))
    # write output
    if fname_ttrees_out is not None:
        log_info('Writing output...')
        writer = YAMLWriter(scenario=None, args={'to': fname_ttrees_out})
        writer.process_document(gen_doc)


def asearch_gen(args):
    """A*search generation"""

    opts, files = getopt(args, 'e:d:')
    eval_file = None
    debug_out = None
    fname_ttrees_out = None
    cfg_file = None

    for opt, arg in opts:
        if opt == '-e':
            eval_file = arg
        elif opt == '-d':
            debug_out = file_stream(arg, mode='w')
        elif opt == '-w':
            fname_ttrees_out = arg
        elif opt == '-c':
            cfg_file = arg

    if len(files) != 3:
        sys.exit('Invalid arguments.\n' + __doc__)
    fname_cand_model, fname_rank_model, fname_da_test = files

    log_info('Initializing...')
    candgen = RandomCandidateGenerator({})
    candgen.load_model(fname_cand_model)
    ranker = PerceptronRanker.load_from_file(fname_rank_model)
    cfg = Config(cfg_file) if cfg_file else {}
    cfg.update({'candgen': candgen, 'debug_out': debug_out, 'ranker': ranker})
    tgen = ASearchPlanner(cfg)

    log_info('Generating...')
    gen_doc = None
    das = read_das(fname_da_test)

    if eval_file is None:
        # just generate
        for da in das:
            gen_doc = tgen.generate_tree(da, gen_doc, None)
    else:
        # generate and evaluate
        eval_ttrees = ttrees_from_doc(read_ttrees(eval_file), tgen.language, tgen.selector)
        for da, eval_ttree in zip(das, eval_ttrees):
            gen_doc = tgen.generate_tree(da, gen_doc, eval_ttree)
        gen_ttrees = ttrees_from_doc(gen_doc, tgen.language, tgen.selector)

        log_info('Evaluating...')
        correct, predicted, gold = 0, 0, 0
        for eval_ttree, gen_ttree in zip(eval_ttrees, gen_ttrees):
            tc, tp, tg = tp_fp_fn(eval_ttree, gen_ttree)
            correct += tc
            predicted += tp
            gold += tg
        log_info("Node precision: %.4f, Recall: %.4f, F1: %.4f" %
                 p_r_f1_from_counts(correct, gold, predicted))

    # write output
    if fname_ttrees_out is not None:
        log_info('Writing output...')
        writer = YAMLWriter(scenario=None, args={'to': fname_ttrees_out})
        writer.process_document(gen_doc)


if __name__ == '__main__':

    random.seed(1206)

    if len(sys.argv) < 3:
        sys.exit(__doc__)

    action = sys.argv[1]
    args = sys.argv[2:]

    if action == 'candgen_train':
        candgen_train(args)
    elif action == 'logregrank_create_data':
        logregrank_create_data(args)
    elif action == 'logregrank_train':
        logregrank_train(args)
    elif action == 'percrank_train':
        percrank_train(args)
    elif action == 'random_gen':
        sample_gen(args)
    elif action == 'asearch_gen':
        asearch_gen(args)
    else:
        # Unknown action
        sys.exit(('ERROR: Unknown action: %s' % action) + __doc__)

    log_info('Done.')