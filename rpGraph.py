import networkx as nx
from networkx.readwrite import json_graph
import logging
import os
import itertools
import numpy as np
import random

'''
logging.basicConfig()
logging.root.setLevel(logging.NOTSET)
logging.basicConfig(level=logging.NOTSET)

logging.basicConfig(
    level=logging.DEBUG,
    #level=logging.WARNING,
    #level=logging.ERROR,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S',
)
'''

## Create hypergraphs using networkx and perform different types of operations on it
#
#
class rpGraph:
    ##
    #
    #
    def __init__(self, rpsbml, pathway_id='rp_pathway', central_species_group_id='central_species', sink_species_group_id='rp_sink_species'):
        self.rpsbml = rpsbml
        self.logger = logging.getLogger(__name__)
        #WARNING: change this to reflect the different debugging levels
        self.logger.debug('Started instance of rpGraph')
        self.pathway_id = pathway_id
        self.central_species_group_id = central_species_group_id
        self.sink_species_group_id = sink_species_group_id
        self.G = None
        self.species = None
        self.reactions = None
        self.pathway_id = pathway_id
        self.num_reactions = 0
        self.central_species = []
        self.sink_species = []
        self.num_species = 0
        self._makeGraph(pathway_id, central_species_group_id, sink_species_group_id)


    ######################################################################################################
    ######################################### Private Function ###########################################
    ######################################################################################################

    ## Compare two rpgraph hypergraphs and return a score using a simple walk
    #
    #
    def _compare(self, source_compare_graph, target_compare_graph):
        import gmatch4py as gm
        #NOTE: here we use the greedy edit distance method but others may be used... 
        ged = gm.GreedyEditDistance(1,1,1,1)
        #ged = gm.GraphEditDistance(1,1,1,1)
        result = ged.compare([i[0] for i in source_compare_graph]+[i[0] for i in target_compare_graph], None)
        self.logger.debug('result: \n'+str([list(i) for i in result]))
        weights = np.array([sum(i[1])/7.0 for i in source_compare_graph]+[sum(i[1])/7.0 for i in target_compare_graph])
        weighted_similarity = np.array([i*weights for i in ged.similarity(result)])
        self.logger.debug('weighted_similarity: \n'+str([list(i) for i in weighted_similarity]))
        #weighted_distance = np.array([i*weights for i in ged.distance(result)])
        #self.logger.debug('weighted_distance: \n'+str([list(i) for i in weighted_distance]))
        filtered_weighted_similarity =  []
        source_pos = [i for i in range(len(source_compare_graph))]
        for i in range(len(weighted_similarity)):
            tmp = []
            for y in range(len(weighted_similarity[i])):
                if i in source_pos and not y in source_pos:
                    tmp.append(weighted_similarity[i][y])
                elif i not in source_pos and y in source_pos:
                    tmp.append(weighted_similarity[i][y])
                else:
                    tmp.append(0.0)
            filtered_weighted_similarity.append(tmp)
        self.logger.debug('filtered_weighted_similarity: \n'+str([list(i) for i in filtered_weighted_similarity]))
        return max(map(max, filtered_weighted_similarity))


    ## Make a special graphs for comparison whit the ID's being unique to the nodes
    #
    # Because comparisong of networkx graphs cannot use the attributes of the nodes, we create graphs based on the EC number 
    # of the reactions and the InChiKeys of the species
    #
    # TODO: if there are multiple EC number and multiple inchikeys, then you should construct all the alternative graphs and
    # compare the, with your target, and return the one that has the highest score. Only then can you 
    def _makeCompareGraphs(self, inchikey_layers=2, ec_layers=3, pathway_id='rp_pathway'):
        #retreive the pathway species and reactions
        species = [self.rpsbml.model.getSpecies(i) for i in self.rpsbml.readUniqueRPspecies(pathway_id)]
        groups = self.rpsbml.model.getPlugin('groups')
        rp_pathway = groups.getGroup(pathway_id)
        reactions = [self.rpsbml.model.getReaction(i.getIdRef()) for i in rp_pathway.getListOfMembers()]
        Gs = []
        #what you want to do is build a series of graphs that have the most info to the least 
        #WARNING: Probably need to checkt that there are no 2 species that have the same inchi_keys at a particular layer
        ###################### Species #######################
        # The species either have their inchikey's or their id's used as name of nodes. If smaller layers are input
        # then the full inchikey and their lower layers are input to build the graphs
        spe_comb = []
        spe_comb_info = []
        if inchikey_layers in [1,2,3]:
            for inch_lay in reversed(range(inchikey_layers, 4)):
                speid_newid = {}
                ############# InChiKey ###############
                for spe in species:
                    brsynth = self.rpsbml.readBRSYNTHAnnotation(spe.getAnnotation())
                    #loop through all the different layers of the inchikey and calculate the graph
                    if 'inchikey' in brsynth:
                        speid_newid[spe.getId()] = '-'.join(i for i in brsynth['inchikey'].split('-')[:inch_lay])
                    else:
                        miriam = self.rpsbml.readMIRIAMAnnotation(spe.getAnnotation())
                        if 'inchikey' in miriam:
                            if len(miriam['inchikey'])>1:
                                self.logger.warning('There are multiple inchikeys for '+str(spe.id)+': '+str(miriam['inchikey']))
                                self.logger.warning('Using the first one')
                            speid_newid[spe.getId()] = '-'.join(i for i in miriam['inchikey'][0].split('-')[:inch_lay])
                        else:
                            self.logger.warning('There is no inchikey associated with species: '+str(spe.getId()))
                            self.logger.warning('Setting species ID as the node id')
                            speid_newid[spe.getId()] = spe.getId()
                spe_comb.append(speid_newid)
                spe_comb_info.append(inch_lay)
        elif inchikey_layers==0:
            speid_newid = {}
            for spe in species:
                speid_newid[spe.getId()] = spe.getId()
            spe_comb.append(speid_newid)
            spe_comb_info.append(3) # ie. full info
        else:
            self.logger.error('Cannot recognise the inchi_layers input: '+str(inchikey_layers))
            return False
        ######################## Reactions ########################
        reac_comb = []
        reac_comb_info = []
        if ec_layers in [1,2,3,4]:
            for ec_lay in reversed(range(ec_layers, 5)):
                reacid_newid = {}
                ############### EC number ################
                for reac in reactions:
                    #brsynth = self.rpsbml.readBRSYNTHAnnotation(reac.getAnnotation())
                    miriam = self.rpsbml.readMIRIAMAnnotation(reac.getAnnotation())
                    reacid_newid[reac.getId()] = []
                    if 'ec-code' in miriam:
                        #WARNING: need to deal with multiple ec numbers....
                        for ec_n in miriam['ec-code']:
                            reacid_newid[reac.getId()].append('.'.join(i for i in ec_n.split('.')[:ec_lay] if not i=='-')) #remove the layers that have '-' characters
                    else:
                        self.logger.warning('There is no EC number associated with reaction: '+str(reac.getId()))
                        self.logger.warning('Setting the id as node name')
                        reacid_newid[reac.getId()] = [reac.getId()] #consider random assignement of reaction id's since these may skew the comparison results
                reac_comb.append(reacid_newid)
                reac_comb_info.append(ec_lay)
        elif ec_layers==0:
            reacid_newid = {}
            reacid_newid[reac.getId()] = [reac.getId()]
            reac_comb.append(reacid_newid)
            reac_comb_info.append(4) #ie. full info
        elif ec_layers==-1:
            reacid_newid = {}
            reacid_newid[reac.getId()] = [brsynth['smiles'].upper()]
            reac_comb.append(reacid_newid)
            reac_comb_info.append(4) # ie. full info
        else:
            self.logger.error('Cannot interpret the ec_layers input: '+str(ec_layers))
            return False
        ###### make the graphs #####
        #remove the duplicates
        for rea in reac_comb:
            for rpx in rea:
                rea[rpx] = list(set(rea[rpx]))
        Gs = []
        #combine the different EC numbers per reaction
        #NOTE: These are ordered lists where the first values have the most info and the other have decreasing amounts
        self.logger.debug('spe_comb: '+str(spe_comb))
        self.logger.debug('spe_comb_info: '+str(spe_comb_info))
        self.logger.debug('reac_comb: '+str(reac_comb))
        self.logger.debug('reac_comb_info: '+str(reac_comb_info))
        self.logger.debug('----------------------------------------')
        for comb, comb_info in zip(list(itertools.product(spe_comb, reac_comb)), list(itertools.product(spe_comb_info, reac_comb_info))):
            self.logger.debug('comb: '+str(comb))
            self.logger.debug('comb_info: '+str(comb_info))
            ids = list(comb[1].keys())
            list_list = [comb[1][i] for i in ids]
            for r in list(itertools.product(*list_list)):
                tmp_reac = {key: value for (key, value) in zip(ids, r)}
                G = nx.DiGraph()
                for spe in species:
                    G.add_node(comb[0][spe.getId()])
                for rea in reactions:
                    G.add_node(tmp_reac[rea.getId()])
                for reaction in reactions:
                    for reac in reaction.getListOfReactants():
                        G.add_edge(comb[0][reac.species],
                                   tmp_reac[reaction.getId()])
                    for prod in reaction.getListOfProducts():
                        G.add_edge(tmp_reac[reaction.getId()],
                                   comb[0][prod.species])
                Gs.append((G, comb_info))
        return Gs


    ################################# Analyse and make graph #####################

    ## Function that converts the object rpSBML to a networkx, with all the MIRIAM and BRSynth annotations passed as attributes
    #
    #
    def _makeGraph(self, pathway_id='rp_pathway', central_species_group_id='central_species', sink_species_group_id='rp_sink_species'):
        self.species = [self.rpsbml.model.getSpecies(i) for i in self.rpsbml.readUniqueRPspecies(pathway_id)]
        groups = self.rpsbml.model.getPlugin('groups')
        c_s = groups.getGroup(central_species_group_id)
        self.central_species = [i.getIdRef() for i in c_s.getListOfMembers()]
        s_s = groups.getGroup(sink_species_group_id)
        self.sink_species = [i.getIdRef() for i in s_s.getListOfMembers()]
        rp_pathway = groups.getGroup(pathway_id)
        self.reactions = [self.rpsbml.model.getReaction(i.getIdRef()) for i in rp_pathway.getListOfMembers()]
        self.G = nx.DiGraph(brsynth=self.rpsbml.readBRSYNTHAnnotation(rp_pathway.getAnnotation()))
        #nodes
        for spe in self.species:
            self.num_species += 1
            is_central = False
            is_sink = False
            if spe.getId() in self.central_species:
                is_central = True
            if spe.getId() in self.sink_species:
                is_sink = True
            self.G.add_node(spe.getId(),
                            type='species',
                            name=spe.getName(),
                            miriam=self.rpsbml.readMIRIAMAnnotation(spe.getAnnotation()),
                            brsynth=self.rpsbml.readBRSYNTHAnnotation(spe.getAnnotation()),
                            central_species=is_central,
                            sink_species=is_sink)
        for reac in self.reactions:
            self.num_reactions += 1
            self.G.add_node(reac.getId(),
                            type='reaction',
                            miriam=self.rpsbml.readMIRIAMAnnotation(reac.getAnnotation()),
                            brsynth=self.rpsbml.readBRSYNTHAnnotation(reac.getAnnotation()))
        #edges
        for reaction in self.reactions:
            for reac in reaction.getListOfReactants():
                self.G.add_edge(reac.species,
                                reaction.getId(),
                                stoichio=reac.stoichiometry)
            for prod in reaction.getListOfProducts():
                self.G.add_edge(reaction.getId(),
                                prod.species,
                                stoichio=reac.stoichiometry)


    ## Return the species ID's that are only consumed in the heterologous pathway
    #
    #
    def _onlyConsumedSpecies(self, only_central=False):
        only_consumed_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            if node['type']=='species':
                if only_central:
                    if node['central_species']==True:
                        if not len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))==0:
                            only_consumed_species.append(node_name)
                else:
                    if not len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))==0:
                        only_consumed_species.append(node_name)
        return only_consumed_species


    ## Return the species ID's that are only produced in the heterologous pathway
    #
    #
    def _onlyProducedSpecies(self, only_central=False):
        only_produced_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            self.logger.debug('node_name: '+str(node_name))
            self.logger.debug('node: '+str(node))
            if node['type']=='species':
                if only_central:
                    if node['central_species']==True:
                        if len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))>0:
                            only_produced_species.append(node_name)
                else:
                    if len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))>0:
                        only_produced_species.append(node_name)
        return only_produced_species


    ## Recursive function that finds the order of the reactions in the graph 
    #
    # NOTE: only works for linear pathways... need to find a better way ie. Tree's
    #
    def _recursiveReacSuccessors(self, node_name, reac_list, all_res, num_reactions):
        current_reac_list = [i for i in reac_list]
        self.logger.debug('-------- '+str(node_name)+' --> '+str(reac_list)+' ----------')
        succ_node_list = [i for i in self.G.successors(node_name)]
        flat_reac_list = [i for sublist in reac_list for i in sublist]
        self.logger.debug('flat_reac_list: '+str(flat_reac_list))
        self.logger.debug('current_reac_list: '+str(current_reac_list))
        if len(flat_reac_list)==num_reactions:
            self.logger.debug('Returning')
            #return current_reac_list
            all_res.append(current_reac_list)
            return all_res
        self.logger.debug('succ_node_list: '+str(succ_node_list))
        if not succ_node_list==[]:
            #can be multiple reactions at a given step
            multi_reac = []
            for n_n in succ_node_list:
                n = self.G.node.get(n_n)
                if n['type']=='reaction':
                    if not n_n in flat_reac_list:
                        multi_reac.append(n_n)
            #remove the ones that already exist
            self.logger.debug('multi_reac: '+str(multi_reac))
            multi_reac = [x for x in multi_reac if x not in flat_reac_list]
            self.logger.debug('multi_reac: '+str(multi_reac))
            if multi_reac:
                current_reac_list.append(multi_reac)
            self.logger.debug('current_reac_list: '+str(current_reac_list))
            #loop through all the possibilities
            for n_n in succ_node_list:
                n = self.G.node.get(n_n)
                if n['type']=='reaction':
                    if n_n in multi_reac:
                        self._recursiveReacSuccessors(n_n, current_reac_list, all_res, num_reactions)
                elif n['type']=='species':
                    if n['central_species']==True:
                        self._recursiveReacSuccessors(n_n, current_reac_list, all_res, num_reactions)
        return all_res


    ##
    #
    # NOTE: only works for linear pathways... need to find a better way
    #
    def _recursiveReacPredecessors(self, node_name, reac_list, all_res, num_reactions):
        current_reac_list = [i for i in reac_list]
        self.logger.debug('-------- '+str(node_name)+' --> '+str(reac_list)+' ----------')
        pred_node_list = [i for i in self.G.predecessors(node_name)]
        flat_reac_list = [i for sublist in reac_list for i in sublist]
        self.logger.debug('flat_reac_list: '+str(flat_reac_list))
        self.logger.debug('current_reac_list: '+str(current_reac_list))
        if len(flat_reac_list)==num_reactions:
            self.logger.debug('Returning')
            #return current_reac_list
            all_res.append(current_reac_list)
            return all_res
        self.logger.debug('pred_node_list: '+str(pred_node_list))
        if not pred_node_list==[]:
            #can be multiple reactions at a given step
            multi_reac = []
            for n_n in pred_node_list:
                n = self.G.node.get(n_n)
                if n['type']=='reaction':
                    if not n_n in flat_reac_list:
                        multi_reac.append(n_n)
            #remove the ones that already exist
            self.logger.debug('multi_reac: '+str(multi_reac))
            multi_reac = [x for x in multi_reac if x not in flat_reac_list]
            self.logger.debug('multi_reac: '+str(multi_reac))
            if multi_reac:
                current_reac_list.append(multi_reac)
            self.logger.debug('current_reac_list: '+str(current_reac_list))
            #loop through all the possibilities
            for n_n in pred_node_list:
                n = self.G.node.get(n_n)
                if n['type']=='reaction':
                    if n_n in multi_reac:
                        self._recursiveReacPredecessors(n_n, current_reac_list, all_res, num_reactions)
                elif n['type']=='species':
                    if n['central_species']==True:
                        self._recursiveReacPredecessors(n_n, current_reac_list, all_res, num_reactions)
        return all_res


    '''
    def _recursiveHierarchy(self, node_name, num_nodes, ranked_nodes):
        self.G.successors(node_name)
    '''

    ######################################################################################################
    ########################################## Public Function ###########################################
    ######################################################################################################

    ############################# graph analysis ################################

    #@staticmethod
    def similarityScore(self, source_rpsbml, target_rpsbml, inchikey_layers=2, ec_layers=3, pathway_id='rp_pathway'):
        source_rpsbml = rpGraph.rpGraph(source_rpsbml)
        target_rpsbml = rpGraph.rpGraph(target_rpsbml)
        source_graphs = source_rpsbml._makeCompareGraphs(inchikey_layers, ec_layers, pathway_id)
        target_graphs = target_rpsbml._makeCompareGraphs(inchikey_layers, ec_layers, pathway_id)
        return rpGraph._compare(source_graphs, target_graphs)


    def exportJSON(self):
        return json_graph.node_link_data(self.G)


    ## Warning that this search algorithm only works for mono-component that are not networks (i.e where reactions follow each other)
    # DEPRECATED: this is linear
    # NOTE: only works for linear pathways... need to find a better way
    #
    def orderedRetroReactions(self):
        #Note: may be better to loop tho
        succ_res = []
        for cons_cent_spe in self._onlyConsumedSpecies():
            res = self._recursiveReacSuccessors(cons_cent_spe, [], [], self.num_reactions)
            if res:
                self.logger.debug(res)
                if len(res)==1:
                    succ_res = res[0]
                else:
                    self.logger.error('Multiple successors results: '+str(res))
            else:
                self.logger.warning('Successors no results')
        prod_res = []
        for prod_cent_spe in self._onlyProducedSpecies():
            res = self._recursiveReacPredecessors(prod_cent_spe, [], [], self.num_reactions)
            if res:
                self.logger.debug(res)
                if len(res)==1:
                    prod_res = [i for i in reversed(res[0])]
                else:
                    self.logger.error('Mutliple predecessors results: '+str(res))
            else:
                self.logger.warning('Predecessors no results')
        if succ_res and prod_res:
            if not succ_res==prod_res:
                self.logger.warning('Both produce results and are not the same')
                self.logger.warning('succ_res: '+str(succ_res))
                self.logger.warning('prod_res: '+str(prod_res))
            else:
                self.logger.debug('Found solution: '+str(succ_res))
                return succ_res
        return []


    ################################################# BELOW IS DEV ################################

    """
    def orderedRetroReac(self):
        for node_name in self.G.nodes:
            node = self.G.nodes.get(node_name)
            if node['type']=='reaction':
                self.logger.debug('---> Starting reaction: '+str(node_name))
                tmp_retrolist = [node_name]
                is_not_end_reac = True
                while is_not_end_reac:
                    tmp_spereacs = []
                    #for all the species, gather the ones that are not valid
                    for spe_name in self.G.predecessors(tmp_retrolist[-1]):
                        spe_node = self.G.nodes.get(spe_name)
                        if spe_node['type']=='reaction':
                            self.logger.warning('Reaction '+str(tmp_retrolist[-1])+' is directly connected to the following reaction '+str(spe_name))
                            continue
                        elif spe_node['type']=='species':
                            if spe_node['central_species']==True:
                                self.logger.debug('\tSpecies: '+str(spe_name))
                                self.logger.debug('\t'+str([i for i in self.G.predecessors(spe_name)]))
                                tmp_spereacs.append([i for i in self.G.predecessors(spe_name)])
                        else:
                            self.logger.warning('Node type should be either reaction or species: '+str(node['type']))
                    #remove empty lists
                    self.logger.debug(tmp_spereacs)
                    tmp_spereacs = [i for i in tmp_spereacs if i != []]
                    self.logger.debug(tmp_spereacs)
                    #return the number of same intersect
                    if tmp_spereacs==[]:
                        is_not_end_reac = False
                        continue
                    tmp_spereacs = list(set.intersection(*map(set, tmp_spereacs)))
                    self.logger.debug(tmp_spereacs)
                    if len(tmp_spereacs)>1:     
                        self.logger.warning('There are multiple matches: '+str(tmp_spereacs))
                    elif len(tmp_spereacs)==0:
                        self.logger.debug('Found the last reaction')
                        is_not_end_reac = False
                    elif len(tmp_spereacs)==1:
                        self.logger.debug('Found the next reaction: '+str(tmp_spereacs[0]))
                        if tmp_spereacs[0] not in tmp_retrolist:
                            tmp_retrolist.append(tmp_spereacs[0])
                        else:
                            self.logger.warning('Trying to add a reaction in the sequence that already exists')
                            is_not_end_reac = False
                    self.logger.debug(tmp_retrolist)
                self.logger.debug('The tmp result is: '+str(tmp_retrolist))
                if len(tmp_retrolist)==self.num_reactions:
                    return tmp_retrolist


    def orderedReac(self):
        for node_name in self.G.nodes:
            node = self.G.nodes.get(node_name)
            if node['type']=='reaction':
                self.logger.debug('---> Starting reaction: '+str(node_name))
                tmp_retrolist = [node_name]
                is_not_end_reac = True
                while is_not_end_reac:
                    tmp_spereacs = []
                    #for all the species, gather the ones that are not valid
                    for spe_name in self.G.successors(tmp_retrolist[-1]):
                        spe_node = self.G.nodes.get(spe_name)
                        if spe_node['type']=='reaction':
                            self.logger.warning('Reaction '+str(tmp_retrolist[-1])+' is directly connected to the following reaction '+str(spe_name))
                            continue
                        elif spe_node['type']=='species':
                            if spe_node['central_species']==True:
                                self.logger.debug('\tSpecies: '+str(spe_name))
                                self.logger.debug('\t'+str([i for i in self.G.successors(spe_name)]))
                                tmp_spereacs.append([i for i in self.G.successors(spe_name)])
                        else:
                            self.logger.warning('Node type should be either reaction or species: '+str(node['type']))
                    #remove empty lists
                    self.logger.debug(tmp_spereacs)
                    tmp_spereacs = [i for i in tmp_spereacs if i!=[]]
                    self.logger.debug(tmp_spereacs)
                    #return the number of same intersect
                    if tmp_spereacs==[]:
                        is_not_end_reac = False
                        continue
                    tmp_spereacs = list(set.intersection(*map(set, tmp_spereacs)))
                    self.logger.debug(tmp_spereacs)
                    if len(tmp_spereacs)>1:     
                        self.logger.warning('There are multiple matches: '+str(tmp_spereacs))
                    elif len(tmp_spereacs)==0:
                        self.logger.debug('Found the last reaction')
                        is_not_end_reac = False
                    elif len(tmp_spereacs)==1:
                        self.logger.debug('Found the next reaction: '+str(tmp_spereacs[0]))
                        if tmp_spereacs[0] not in tmp_retrolist:
                            tmp_retrolist.append(tmp_spereacs[0])
                        else:
                            self.logger.warning('Trying to add a reaction in the sequence that already exists')
                            is_not_end_reac = False
                    self.logger.debug(tmp_retrolist)
                self.logger.debug('The tmp result is: '+str(tmp_retrolist))
                if len(tmp_retrolist)==self.num_reactions:
                    return tmp_retrolist
        """
