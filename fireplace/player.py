import random
from itertools import chain
from .actions import Draw, Give, Steal, Summon
from .card import Card
from .deck import Deck
from .entity import Entity
from .enums import CardType, PlayState, Zone
from .entity import slot_property
from .managers import PlayerManager
from .targeting import *
from .utils import CardList


class Player(Entity):
	Manager = PlayerManager
	extra_deathrattles = slot_property("extra_deathrattles")
	healing_double = slot_property("healing_double", sum)
	hero_power_double = slot_property("hero_power_double", sum)
	outgoing_healing_adjustment = slot_property("outgoing_healing_adjustment")
	spellpower_double = slot_property("spellpower_double", sum)
	type = CardType.PLAYER

	def __init__(self, name):
		self.data = None
		super().__init__()
		self.name = name
		self.deck = Deck()
		self.hand = CardList()
		self.field = CardList()
		self.graveyard = CardList()
		self.secrets = CardList()
		self.buffs = []
		self.choice = None
		self.start_hand_size = 4
		self.max_hand_size = 10
		self.max_resources = 10
		self.cant_draw = False
		self.cant_fatigue = False
		self.fatigue_counter = 0
		self.hero = None
		self.last_card_played = None
		self.overloaded = 0
		self._max_mana = 0
		self.playstate = PlayState.INVALID
		self.temp_mana = 0
		self.timeout = 75
		self.times_hero_power_used_this_game = 0
		self.minions_killed_this_turn = 0
		self.weapon = None
		self.zone = Zone.INVALID

	def __str__(self):
		return self.name

	def __repr__(self):
		return "%s(name=%r, hero=%r)" % (self.__class__.__name__, self.name, self.hero)

	@property
	def current_player(self):
		return self.game.current_player is self

	@property
	def controller(self):
		return self

	@property
	def slots(self):
		return self.buffs

	@property
	def mana(self):
		mana = max(0, self.max_mana - self.used_mana - self.overload_locked) + self.temp_mana
		return mana

	@property
	def heropower_damage(self):
		return sum(minion.heropower_damage for minion in self.field)

	@property
	def spellpower(self):
		return sum(minion.spellpower for minion in self.field)

	@property
	def characters(self):
		return CardList(chain([self.hero] if self.hero else [], self.field))

	@property
	def entities(self):
		ret = []
		for entity in self.field:
			ret += entity.entities
		ret += self.secrets
		return CardList(chain(list(self.hero.entities) if self.hero else [], ret, [self]))

	@property
	def live_entities(self):
		ret = self.field[:]
		if self.hero:
			ret.append(self.hero)
		if self.weapon:
			ret.append(self.weapon)
		return ret

	@property
	def minion_slots(self):
		return max(0, self.game.MAX_MINIONS_ON_FIELD - len(self.field))

	def card(self, id, source=None, zone=Zone.SETASIDE):
		card = Card(id)
		card.controller = self
		card.zone = zone
		if source is not None:
			card.creator = source
		self.game.manager.new_entity(card)
		return card

	def get_spell_damage(self, amount: int) -> int:
		"""
		Returns the amount of damage \a amount will do, taking
		SPELLPOWER and SPELLPOWER_DOUBLE into account.
		"""
		amount += self.spellpower
		amount *= (self.controller.spellpower_double + 1)
		return amount

	def give(self, id):
		cards = self.game.queue_actions(self, [Give(self, id)])[0]
		return cards[0][0]

	def prepare_deck(self, cards, hero):
		self.starting_deck = cards
		self.starting_hero = hero

	def discard_hand(self):
		self.log("%r discards their entire hand!", self)
		# iterate the list in reverse so we don't skip over cards in the process
		# yes it's stupid.
		for card in self.hand[::-1]:
			card.discard()

	def draw(self, count=1):
		if self.cant_draw:
			self.log("%s tries to draw %i cards, but can't draw", self, count)
			return None

		ret = self.game.queue_actions(self, [Draw(self) * count])[0]
		if count == 1:
			if not ret[0]:  # fatigue
				return None
			return ret[0][0]
		return ret

	def mill(self, count=1):
		if count == 1:
			if not self.deck:
				return
			else:
				card = self.deck[-1]
			self.log("%s mills %r", self, card)
			card.discard()
			return card
		else:
			ret = []
			while count:
				ret.append(self.mill())
				count -= 1
			return ret

	def fatigue(self):
		if self.cant_fatigue:
			self.log("%s can't fatigue and does not take damage", self)
			return
		self.fatigue_counter += 1
		self.log("%s takes %i fatigue damage", self, self.fatigue_counter)
		self.hero.hit(self.hero, self.fatigue_counter)

	@property
	def max_mana(self):
		return self._max_mana

	@max_mana.setter
	def max_mana(self, amount):
		self._max_mana = min(self.max_resources, max(0, amount))
		self.log("%s is now at %i mana crystals", self, self._max_mana)

	def steal(self, card):
		return self.game.queue_actions(self, [Steal(card)])

	def shuffle_deck(self):
		self.log("%r shuffles their deck", self)
		random.shuffle(self.deck)

	def summon(self, card):
		"""
		Puts \a card in the PLAY zone
		"""
		if isinstance(card, str):
			card = self.card(card, zone=Zone.PLAY)
		self.game.queue_actions(self, [Summon(self, card)])
		return card
