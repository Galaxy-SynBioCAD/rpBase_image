import networkx as nx
import logging


class rpGraph:
    """The class that hosts the networkx related functions
    """
    def __init__(self, rpsbml, pathway_id='rp_pathway', species_group_id='central_species'):
        """Constructor of the class

        Automatically constructs the network when calling the construtor

        :param rpsbml: The rpSBML object
        :param pathway_id: The pathway id of the heterologous pathway
        :param species_group_id: The id of the central species

        :type rpsbml: rpSBML
        :type pathway_id: str
        :type species_group_id: str
        """
        self.rpsbml = rpsbml
        self.logger = logging.getLogger(__name__)
        #WARNING: change this to reflect the different debugging levels
        self.logger.debug('Started instance of rpGraph')
        self.pathway_id = pathway_id
        self.species_group_id = species_group_id
        self.G = None
        self.species = None
        self.reactions = None
        self.pathway_id = pathway_id
        self.num_reactions = 0
        self.num_species = 0
        self._makeGraph(pathway_id, species_group_id)


    def _makeGraph(self, pathway_id='rp_pathway', species_group_id='central_species'):
        """Private function that constructs the networkx graph

        :param pathway_id: The pathway id of the heterologous pathway
        :param species_group_id: The id of the central species

        :type pathway_id: str
        :type species_group_id: str

        :return: None
        :rtype: None
        """
        self.species = [self.rpsbml.model.getSpecies(i) for i in self.rpsbml.readUniqueRPspecies(pathway_id)]
        groups = self.rpsbml.model.getPlugin('groups')
        central_species = groups.getGroup(species_group_id)
        central_species = [i.getIdRef() for i in central_species.getListOfMembers()]
        rp_pathway = groups.getGroup(pathway_id)
        self.reactions = [self.rpsbml.model.getReaction(i.getIdRef()) for i in rp_pathway.getListOfMembers()]
        self.G = nx.DiGraph(brsynth=self.rpsbml.readBRSYNTHAnnotation(rp_pathway.getAnnotation()))
        #nodes
        for spe in self.species:
            self.num_species += 1
            is_central = False
            if spe.getId() in central_species:
                is_central = True
            self.G.add_node(spe.getId(), 
                            type='species',
                            name=spe.getName(),
                            miriam=self.rpsbml.readMIRIAMAnnotation(spe.getAnnotation()),
                            brsynth=self.rpsbml.readBRSYNTHAnnotation(spe.getAnnotation()),
                            central_species=is_central)
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


    def _onlyConsumedSpecies(self):
        """Private function that returns the single parent species that are consumed only

        :return: List of node ids
        :rtype: list
        """
        only_consumed_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            if node['type']=='species':
                if not len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))==0:
                    only_consumed_species.append(node_name)
        return only_consumed_species


    def _onlyConsumedCentralSpecies(self):
        """Private function that returns the single parent central consumed species

        :return: List of node ids
        :rtype: list
        """
        only_consumed_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            if node['type']=='species':
                if node['central_species']==True:
                    if not len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))==0:
                        only_consumed_species.append(node_name)
        return only_consumed_species


    def _onlyProducedSpecies(self):
        """Private function that returns the single parent produced species

        :return: List of node ids
        :rtype: list
        """
        only_produced_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            if node['type']=='species':
                if len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))>0:
                    only_produced_species.append(node_name)
        return only_produced_species


    def _onlyProducedCentralSpecies(self):
        """Private function that returns the single parent produced central species

        :return: List of node ids
        :rtype: list
        """
        only_produced_species = []
        for node_name in self.G.nodes():
            node = self.G.node.get(node_name)
            if node['type']=='species':
                if node['central_species']==True:
                    if len(list(self.G.successors(node_name)))==0 and len(list(self.G.predecessors(node_name)))>0:
                        only_produced_species.append(node_name)
        return only_produced_species


    def _recursiveReacPredecessors(self, node_name, reac_list):
        """Return the next linear predecessors

        Better than before, however bases itself on the fact that central species do not have multiple predesessors
        if that is the case then the algorithm will return badly ordered reactions

        :param node_name: The id of the starting node
        :param reac_list: The list of reactions that already have been run

        :type node_name: str
        :type reac_list: list

        :return: List of node ids
        :rtype: list
        """
        self.logger.debug('-------- '+str(node_name)+' --> '+str(reac_list)+' ----------')
        pred_node_list = [i for i in self.G.predecessors(node_name)]
        self.logger.debug(pred_node_list)
        if pred_node_list==[]:
            return reac_list
        for n_n in pred_node_list:
            n = self.G.node.get(n_n)
            if n['type']=='reaction':
                if n_n in reac_list:
                    return reac_list
                else:
                    reac_list.append(n_n)
                    self._recursiveReacPredecessors(n_n, reac_list)
            elif n['type']=='species':
                if n['central_species']==True:
                    self._recursiveReacPredecessors(n_n, reac_list)
                else:
                    return reac_list
        return reac_list


    def orderedRetroReactions(self):
        """Public function to return the linear list of reactions

        :return: List of node ids
        :rtype: list
        """
        #Note: may be better to loop tho
        for prod_spe in self._onlyProducedSpecies():
            self.logger.debug('Testing '+str(prod_spe))
            ordered = self._recursiveReacPredecessors(prod_spe, [])
            self.logger.debug(ordered)
            if len(ordered)==self.num_reactions:
                return [i for i in reversed(ordered)]
        self.logger.error('Could not find the full ordered reactions')
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
