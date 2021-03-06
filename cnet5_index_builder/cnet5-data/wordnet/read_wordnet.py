from itertools import chain
from collections import defaultdict
from conceptnet5.nodes import make_concept_uri
from conceptnet5.edges import make_edge, MultiWriter, FlatEdgeWriter
import re

mapping = {}
labels = {}
prefixes = {}
glossary = {}
synset_senses = defaultdict(list)
synset_sense_names = defaultdict(list)
sense_name_synsets = defaultdict(list)
sense_synsets = defaultdict(list)

parts_of_speech = {
    'noun': 'n',
    'verb': 'v',
    'adjective': 'a',
    'adjectivesatellite': 'a',
    'adverb': 'r',
}

rel_mapping = {
    'attribute': 'Attribute',
    'causes': 'Causes',
    'classifiedByRegion': 'HasContext',
    'classifiedByUsage': 'HasContext',
    'classifiedByTopic': 'HasContext',
    'entails': 'Entails',
    'hyponymOf': 'IsA',
    'instanceOf': 'InstanceOf',
    'memberMeronymOf': 'MemberOf',
    'partMeronymOf': 'PartOf',
    'sameVerbGroupAs': 'SimilarTo',
    'similarTo': 'SimilarTo',
    'substanceMeronymOf': '~MadeOf',
    'antonymOf': 'Antonym',
    'derivationallyRelated': '~DerivedFrom',
    'pertainsTo': 'PertainsTo',
    'seeAlso': 'RelatedTo',
}

def resolve_prefix(entry):
    prefix, name = entry.split(':')
    return prefixes[prefix] + name

def handle_line(line):
    """
    Get the (subj, obj, pred) parts of a line, unless it's a blank line
    or a prefix definition, in which case return None.
    """
    line = line.decode('utf-8').strip()
    if not line:
        return None
    parts = line.split(None, 2)
    if parts[0] == '@prefix':
        prefix = parts[1].strip(': ')
        value = parts[2].strip('<>. ')
        prefixes[prefix] = value
        return None
    return parts[0], parts[1], parts[2].strip('. ')

# First, get the human-readable label and gloss for every synset.
for line in chain(
    open('raw_data/wordnet-synset.ttl'),
    open('raw_data/full/wordnet-wordsensesandwords.ttl'),
    open('raw_data/wordnet-glossary.ttl')
):
    parts = handle_line(line)
    if parts is None:
        continue
    if parts[1] == 'rdfs:label':
        subj = resolve_prefix(parts[0])
        obj = parts[2].split('"')[1]
        labels[subj] = obj
    elif parts[1] == 'wn20schema:gloss':
        subj = resolve_prefix(parts[0])
        obj = parts[2].split('"')[1]
        glossary[subj] = obj.split(';')[0]
        while '(' in glossary[subj] and ')' in glossary[subj]:
            glossary[subj] = re.sub(r"\([^)]+\) ?", r"", glossary[subj])

# Get the list of word senses in each synset, and make a bidirectional mapping.
for line in open('raw_data/full/wordnet-wordsense-synset-relations.ttl'):
    parts = handle_line(line)
    if parts is None:
        continue
    if parts[1] == 'wn20schema:containsWordSense':
        subj = resolve_prefix(parts[0])
        obj = resolve_prefix(parts[2].strip('. '))
        synset_senses[subj].append(obj)
        sense_synsets[obj] = subj
        sense_name = labels[obj]
        synset_sense_names[subj].append(sense_name)
        sense_name_synsets[sense_name].append(subj)

# Assign every synset a disambiguation name.
for synset in synset_senses:
    senses = sorted(synset_senses[synset])
    synset_name = labels[synset]
    synset_pos = synset.split('-')[-2]
    pos = parts_of_speech[synset_pos]
    disambig = glossary[synset].replace('/', '_')
    # TODO: take into account domains, etc.
    #
    #if len(sense_name_synsets[synset_name]) > 1:
    #    for sense in senses:
    #        sense_name = labels[sense]
    #        more_synsets = sense_name_synsets[sense_name]
    #        if len(more_synsets) == 1:
    #            disambig = sense_name
    #            break
    #    if disambig is None:
    #        disambig = glossary[synset]
    #if disambig is None:
    #    disambig = '*'
    node = make_concept_uri(synset_name, 'en', pos+'/'+disambig)
    if synset not in mapping:
        mapping[synset] = node

# Map senses to the same nodes.
for sense, synset in sense_synsets.items():
    mapping[sense] = mapping[synset]

sources = ['/s/wordnet/3.0']
writer = MultiWriter('wordnet3')
sw_map = FlatEdgeWriter('data/sw/wordnet30.map.json')
sw_map_used = set()

for line in chain(
    open('raw_data/wordnet-attribute.ttl'),
    open('raw_data/wordnet-causes.ttl'),
    open('raw_data/wordnet-classifiedby.ttl'),
    open('raw_data/wordnet-entailment.ttl'),
    open('raw_data/wordnet-hyponym.ttl'),
    open('raw_data/wordnet-instances.ttl'),
    open('raw_data/wordnet-membermeronym.ttl'),
    open('raw_data/wordnet-partmeronym.ttl'),
    open('raw_data/wordnet-sameverbgroupas.ttl'),
    open('raw_data/wordnet-similarity.ttl'),
    open('raw_data/wordnet-substancemeronym.ttl'),
    open('raw_data/full/wordnet-antonym.ttl'),
    open('raw_data/full/wordnet-derivationallyrelated.ttl'),
    open('raw_data/full/wordnet-participleof.ttl'),
    open('raw_data/full/wordnet-pertainsto.ttl'),
    open('raw_data/full/wordnet-seealso.ttl'),
):
    parts = handle_line(line)
    if parts is None:
        continue
    web_subj = resolve_prefix(parts[0])
    web_rel = resolve_prefix(parts[1])
    web_obj = resolve_prefix(parts[2])
    subj = mapping[web_subj]
    obj = mapping[web_obj]
    pred_label = parts[1].split(':')[-1]
    if pred_label in rel_mapping:
        mapped = rel_mapping[pred_label]
        if mapped.startswith('~'):
            subj, obj = obj, subj
            web_subj, web_obj = web_obj, web_subj
            web_rel = web_rel.replace('meronym', 'holonym')
            mapped = mapped[1:]
        pred = '/r/'+mapped
    else:
        pred = '/r/wordnet/'+pred_label

    if (web_rel, pred) not in sw_map_used:
        sw_map.write({'from': web_rel, 'to': pred})
    if (web_subj, subj) not in sw_map_used:
        sw_map.write({'from': web_subj, 'to': subj})
    if (web_obj, obj) not in sw_map_used:
        sw_map.write({'from': web_obj, 'to': obj})

    edge = make_edge(
        pred, subj, obj, '/d/wordnet/3.0',
        license='/l/CC/By', sources=sources,
        context='/ctx/all', weight=2.0
    )
    writer.write(edge)

writer.close()
sw_map.close()

